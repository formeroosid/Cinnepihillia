import logging
from pathlib import Path

from cinephillia.core.media_analyzer import detect_resolution
from cinephillia.core.ffmpeg_profiles import select_preset
from cinephillia.core.ffmpeg_runner import encode_with_profile
from cinephillia.shared.file_ops import ensure_dir_permissions
from cinephillia.tv.disc_parser import parse_tv_input
from cinephillia.tv.episode_classifier import classify_titles
from cinephillia.tv.filebot_renamer import rename_with_query
from cinephillia.tv.inventory import inventory_report, print_inventory

log = logging.getLogger(__name__)

def _prepare_rename_staging(staging_dir, series_name):
    staging_dir = Path(staging_dir)
    rename_dir = staging_dir / "_filebot_stage"

    if rename_dir.exists():
        for old_link in rename_dir.iterdir():
            if old_link.is_symlink() or old_link.is_file():
                old_link.unlink()
    rename_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(staging_dir.rglob("*.mkv"))
    files = [f for f in files if "_filebot_stage" not in str(f)]

    for i, f in enumerate(files, 1):
        link = rename_dir / f"{series_name} - E{i:02d}.mkv"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(f.resolve())
        log.info("Staging symlink: %s -> %s", link.name, f)

    log.info("Prepared %d files for FileBot rename", len(files))
    return rename_dir


def _safe_relative(path, root):
    path = Path(path)
    root = Path(root)
    if path.is_relative_to(root):
        return path.relative_to(root)
    return Path(path.name)


def process_tv_series(
    input_root,
    staging_dir,
    output_root,
    series_name,
    duration_min=None,
    duration_max=None,
    plex_host=None,
    encode_profile=None,
    dry_run=False,
):
    input_root = Path(input_root)
    staging_dir = Path(staging_dir)
    output_root = Path(output_root)

    titles = parse_tv_input(input_root)

    if duration_min is None and duration_max is None:
        episodes = titles
    else:
        episodes, _extras = classify_titles(titles, (duration_min, duration_max))

    pre_report = inventory_report(series_name, ripped_episodes=episodes)
    print_inventory(pre_report)

    if dry_run:
        return pre_report

    staging_dir.mkdir(parents=True, exist_ok=True)

    for ep in episodes:
        src = Path(ep["path"])

        # Detect resolution and choose a profile dict, same as movies
        width, height = detect_resolution(str(src))
        profile = select_preset(width, height)

        rel_path = src.relative_to(input_root)
        output_file = staging_dir / rel_path.with_suffix(".mkv")

        ensure_dir_permissions(str(output_file.parent))

        if output_file.exists() and output_file.stat().st_size > 0:
            log.info("Skipping (already encoded): %s", output_file)
            continue

        log.info(
            "Encoding TV episode: %s -> %s using profile %s",
            src,
            output_file,
            profile.get("name", "<unknown>"),
        )
        encode_with_profile(str(src), str(output_file), profile)

    output_root.mkdir(parents=True, exist_ok=True)
    rename_dir = _prepare_rename_staging(staging_dir, series_name)

    rename_with_query(
        input_dir=rename_dir,
        output_root=output_root,
        series_name=series_name,
        series_format="Season {s}/{n} - {s00e00} - {t}",
    )

    plex_matches = list(output_root.glob(f"{series_name}*"))
    if plex_matches:
        post_report = inventory_report(
            series_name,
            plex_series_root=plex_matches[0],
        )
        print_inventory(post_report)
        return post_report

    return pre_report