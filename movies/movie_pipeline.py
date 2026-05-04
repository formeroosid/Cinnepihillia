import os
import re
import sys
import logging

from core.media_analyzer import detect_resolution
from core.ffmpeg_profiles import select_preset, EXTRAS_PRESET_NAME
from core.ffmpeg_runner import encode_with_profile, encode_extra
from shared.file_ops import ensure_dir_permissions

log = logging.getLogger(__name__)

EXTRA_FOLDERS = [
    "Behind The Scenes", "Deleted Scenes", "Featurettes",
    "Interviews", "Other", "Shorts", "Trailers",
]


def get_movie_info(root_path):
    """Extract title and year from folder name like 'Movie Title (2024)'."""
    base = os.path.basename(root_path.rstrip(os.sep))
    if " (" in base and base.endswith(")"):
        title, year = base.rsplit(" (", 1)
        year = year.rstrip(")")
        return title, year
    return base, ""


def identify_main_feature(files):
    """The largest MKV is assumed to be the main feature."""
    return max(files, key=lambda x: os.path.getsize(x)) if files else None


def process_main_feature(src, out_dir, title, year, preset):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{title} ({year}).mkv")

    # ffmpeg_runner will handle audio/sub detection & mapping.
    log.info(f"Encoding main feature: {src} → {output_file} using profile {preset['name']}")
    encode_with_profile(src, output_file, preset)

def process_extra(src, out_dir, base):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{base}.mkv")
    encode_extra(src, output_file, EXTRAS_PRESET_NAME)


def process_movie(movie_root, mode="both"):
    """Main entry point for movie processing."""
    title, year = get_movie_info(movie_root)
    rip_path = os.path.join(movie_root, "rip")
    plex_root = os.path.join(movie_root, "Plex Movie Files")

    if not os.path.isdir(rip_path):
        msg = f"ERROR: rip folder not found: {rip_path}"
        log.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    movies = [f for f in os.listdir(rip_path) if f.lower().endswith(".mkv")]
    full_paths = [os.path.join(rip_path, f) for f in movies]
    log.info(f"Rip path: {rip_path}")
    log.info(f"MKV files found: {movies}")

    if not full_paths:
        log.warning(f"No MKV files in: {rip_path}")
        return

    main_feature = identify_main_feature(full_paths)
    extras = [f for f in full_paths if f != main_feature]

    # --- Main feature ---
    if mode in ("feature", "both") and main_feature:
        width, height = detect_resolution(main_feature)
        preset = select_preset(width, height)
        process_main_feature(main_feature, plex_root, title, year, preset)

    # --- Extras ---
    if mode in ("extras", "both"):
        for extra in extras:
            extra_base = os.path.splitext(os.path.basename(extra))[0]
            assigned = False
            for folder in sorted(EXTRA_FOLDERS, key=len, reverse=True):
                folder_token = folder.replace(" ", "[ _-]").lower()
                pattern = re.compile(rf"(.+)[ _-]{folder_token}$", re.IGNORECASE)
                match = pattern.match(extra_base)
                if match:
                    trimmed_name = match.group(1).strip(" _-")
                    out_dir = os.path.join(plex_root, folder)
                    process_extra(extra, out_dir, trimmed_name)
                    assigned = True
                    break
            if not assigned:
                out_dir = os.path.join(plex_root, "Other")
                process_extra(extra, out_dir, extra_base)
