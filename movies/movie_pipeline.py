# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import os
import re
import sys
import logging

from core.media_analyzer import detect_resolution
from core.ffmpeg_profiles import select_preset, EXTRAS_PRESET_NAME
from core.ffmpeg_runner import encode_with_profile
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


def process_main_feature(src, out_dir, title, year, preset,
                         preserve_all_audio=False,
                         dolby_vision="auto", dry_run=False):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{title} ({year}).mkv")
    log.info(f"Encoding main feature: {src} → {output_file} using profile {preset['name']}")
    encode_with_profile(src, output_file, preset,
                        preserve_all_audio=preserve_all_audio,
                        dolby_vision=dolby_vision,
                        dry_run=dry_run)


def process_extra(src, out_dir, base,
                  preserve_all_audio=False,
                  dolby_vision="auto", dry_run=False,
                  encoder="native"):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{base}.mkv")
    # Keep the existing HD profile for extras, regardless of source resolution.
    preset = select_preset(1920, 1080, encoder=encoder)
    log.info("Encoding extra with preset '%s' (BluRay profile; backend=%s).",
             EXTRAS_PRESET_NAME, encoder)
    encode_with_profile(src, output_file, preset,
                        preserve_all_audio=preserve_all_audio,
                        dolby_vision=dolby_vision,
                        dry_run=dry_run)


def process_movie(movie_root, mode="both", preserve_all_audio=False,
                  dolby_vision="auto", dry_run=False, encoder="native"):
    """Process movie features/extras with native or NVIDIA HEVC profiles.

    Audio, subtitles, chapters, preflight and Dolby Vision handling remain
    delegated to the shared encoder runner. Only UHD profiles engage DV.
    """
    if encoder not in {"native", "nvenc"}:
        raise ValueError(f"Unsupported encoder backend: {encoder!r}")
    log.info("Movie encoder backend: %s", encoder)
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
    if preserve_all_audio:
        log.info("preserve-all-audio: enabled for movie '%s (%s)' — every audio "
                 "track will be copied", title, year or "????")
    main_feature = identify_main_feature(full_paths)
    extras = [f for f in full_paths if f != main_feature]

    if mode in ("feature", "both") and main_feature:
        width, height = detect_resolution(main_feature)
        preset = select_preset(width, height, encoder=encoder)
        process_main_feature(main_feature, plex_root, title, year, preset,
                             preserve_all_audio=preserve_all_audio,
                             dolby_vision=dolby_vision,
                             dry_run=dry_run)

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
                    process_extra(extra, out_dir, trimmed_name,
                                  preserve_all_audio=preserve_all_audio,
                                  dolby_vision=dolby_vision,
                                  dry_run=dry_run,
                                  encoder=encoder)
                    assigned = True
                    break
            if not assigned:
                out_dir = os.path.join(plex_root, "Other")
                process_extra(extra, out_dir, extra_base,
                              preserve_all_audio=preserve_all_audio,
                              dolby_vision=dolby_vision,
                              dry_run=dry_run,
                              encoder=encoder)
