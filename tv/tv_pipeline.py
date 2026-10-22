# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import logging
from collections import defaultdict
from pathlib import Path

from core.media_analyzer import detect_resolution
from core.ffmpeg_profiles import select_preset
from core.ffmpeg_runner import encode_with_profile
from shared.file_ops import ensure_dir_permissions
from tv.disc_parser import parse_tv_input
from tv.episode_classifier import classify_titles
from tv.inventory import (
    inventory_report,
    print_inventory,
    print_sequential_inventory,
    sequential_inventory_report,
)

log = logging.getLogger(__name__)


def _safe_relative(path, root):
    path = Path(path)
    root = Path(root)
    if path.is_relative_to(root):
        return path.relative_to(root)
    return Path(path.name)


def _default_expected_counts(episodes):
    counts = defaultdict(int)
    for ep in episodes:
        counts[int(ep["season"])] += 1
    return dict(counts)


def _render_sequential_files(output_root, series_name, episodes):
    output_root = Path(output_root)
    rendered = []
    episodes_by_season = defaultdict(list)
    for ep in sorted(episodes, key=lambda e: (e["season"], e["disc"], e["title_num"], str(e["path"]))):
        episodes_by_season[int(ep["season"])].append(ep)
    for season, season_eps in sorted(episodes_by_season.items()):
        season_folder = "Season" if season == 0 else f"Season {season}"
        season_dir = output_root / season_folder
        ensure_dir_permissions(str(season_dir))
        for episode_num, ep in enumerate(season_eps, 1):
            src = Path(ep.get("encoded_path") or ep["path"])
            dest = season_dir / f"{series_name} S{season:02d}E{episode_num:02d}_.mkv"
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.symlink_to(src.resolve())
            rendered.append({"season": season, "episode": episode_num,
                             "source": str(src), "output": str(dest)})
            log.info("Rendered sequential TV file: %s -> %s", dest, src)
    return rendered


def process_tv_series(
    input_root,
    staging_dir,
    output_root,
    series_name,
    preserve_all_audio=False,
    duration_min=None,
    duration_max=None,
    plex_host=None,
    encode_profile=None,
    dry_run=False,
    expected_counts=None,
    use_metadata_rename=False,
    encoder="native",
    dolby_vision="auto",
):
    if encoder not in {"native", "nvenc"}:
        raise ValueError(f"Unsupported encoder backend: {encoder!r}")
    if dolby_vision not in {"auto", "off", "p81", "p76"}:
        raise ValueError(f"Unsupported Dolby Vision mode: {dolby_vision!r}")
    log.info("TV encoder backend: %s; Dolby Vision mode: %s", encoder, dolby_vision)
    input_root = Path(input_root)
    staging_dir = Path(staging_dir)
    output_root = Path(output_root)
    titles = parse_tv_input(input_root)
    if duration_min is None and duration_max is None:
        episodes = titles
    else:
        episodes, _extras = classify_titles(titles, (duration_min, duration_max))
    local_expected = expected_counts or _default_expected_counts(episodes)
    pre_report = sequential_inventory_report(
        series_name, expected_counts=local_expected, ripped_episodes=episodes)
    print_sequential_inventory(pre_report, heading="TV RIP TALLY")
    if preserve_all_audio:
        log.info("preserve-all-audio: enabled — every audio track will be copied "
                 "for all episodes in series '%s'", series_name)
    if dry_run:
        log.info("TV dry-run is inventory-only; encoder preflight and DV planning are not run.")
        return pre_report
    staging_dir.mkdir(parents=True, exist_ok=True)
    encoded_episodes = []
    for ep in sorted(episodes, key=lambda e: (e["season"], e["disc"], e["title_num"], str(e["path"]))):
        src = Path(ep["path"])
        width, height = detect_resolution(str(src))
        profile = select_preset(width, height, encoder=encoder)
        rel_path = src.relative_to(input_root)
        output_file = staging_dir / rel_path.with_suffix(".mkv")
        ensure_dir_permissions(str(output_file.parent))
        if output_file.exists() and output_file.stat().st_size > 0:
            log.warning("Skipping existing nonempty staging file: %s; requested encoder=%s "
                        "and Dolby Vision=%s are NOT applied or verified. Use a fresh "
                        "staging directory to test new settings.", output_file, encoder, dolby_vision)
        else:
            log.info("Encoding TV episode: %s -> %s using profile %s (backend=%s)",
                     src, output_file, profile.get("name", "<unknown>"), encoder)
            result = encode_with_profile(
                str(src), str(output_file), profile,
                preserve_all_audio=preserve_all_audio,
                dolby_vision=dolby_vision,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"TV encode failed (rc={result.returncode}) for {src}; "
                    "stopping before rendering Plex links")
            if not output_file.is_file() or output_file.stat().st_size == 0:
                raise RuntimeError(
                    f"TV encode produced no nonempty staging file for {src}; "
                    "stopping before rendering Plex links")
        ep_copy = dict(ep)
        ep_copy["encoded_path"] = str(output_file)
        encoded_episodes.append(ep_copy)
    output_root.mkdir(parents=True, exist_ok=True)
    if use_metadata_rename:
        pre_metadata_report = inventory_report(series_name, ripped_episodes=episodes)
        print_inventory(pre_metadata_report)
        return pre_metadata_report
    rendered_files = _render_sequential_files(output_root, series_name, encoded_episodes)
    post_report = sequential_inventory_report(
        series_name, expected_counts=local_expected,
        ripped_episodes=episodes, rendered_files=rendered_files)
    print_sequential_inventory(post_report, heading="TV RENDER TALLY")
    return post_report
