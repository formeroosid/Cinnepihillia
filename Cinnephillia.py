# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

#!/usr/bin/env python3
"""Cinnephillia — Movie & TV processing entry point."""
import argparse
from pathlib import Path

from shared.logging_config import setup_logging
from movies.movie_pipeline import process_movie
from tv.tv_pipeline import process_tv_series


def main():
    parser = argparse.ArgumentParser(description="Cinnephillia media processor")
    parser.add_argument("path", help="Path to Movie Title (YYYY) or TV series root")
    parser.add_argument(
        "--mode", choices=["feature", "extras", "both"], default="both",
        help="Process main feature, extras, or both (movie mode only).",
    )
    parser.add_argument(
        "--type", choices=["movie", "tv"], default="movie",
        help="Content type: movie or tv.",
    )
    parser.add_argument(
        "--series-name",
        help="Optional override for TV series name (defaults to folder name).",
    )
    parser.add_argument(
        "--preserve-all-audio", action="store_true",
        help="Map and losslessly copy every audio track (commentary, "
             "alternate languages). Default: keep only the primary track.",
    )
    parser.add_argument(
        "--dolby-vision", choices=["auto", "off", "p81", "p76"], default="auto",
        help="Dolby Vision handling for UHD sources. 'auto' (default) "
             "preserves DV as Profile 8.1 when the source has a DV RPU and "
             "dovi_tool is available; otherwise falls through to HDR10. "
             "'off' skips DV entirely. 'p81'/'p76' force preservation and "
             "error out if the source has no DV or dovi_tool is missing. "
             "Only affects the UHD profile.",
    )
    parser.add_argument(
        "--encoder", choices=["native", "nvenc"], default="native",
        help="Movie video-encoding backend. 'native' preserves x265 for HD/UHD "
             "and VAAPI for SD. 'nvenc' uses NVIDIA HEVC on GPU 0 for features "
             "and extras. NVENC is not yet supported in TV mode.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log every ffmpeg / dovi_tool command without executing it.",
    )
    args = parser.parse_args()
    if args.type == "tv" and args.encoder != "native":
        parser.error("--encoder nvenc is currently supported only for --type movie")

    setup_logging()
    root = Path(args.path)
    if args.type == "movie":
        process_movie(
            str(root), args.mode,
            preserve_all_audio=args.preserve_all_audio,
            dolby_vision=args.dolby_vision,
            dry_run=args.dry_run,
            encoder=args.encoder,
        )
        return

    series_name = args.series_name or root.name
    process_tv_series(
        input_root=str(root / "rip"),
        staging_dir=str(root / "process" / "staging"),
        output_root=str(root / "Plex Movie Files"),
        series_name=series_name,
        duration_min=None,
        duration_max=None,
        plex_host=None,
        encode_profile=None,
        dry_run=args.dry_run,
        expected_counts=None,
        use_metadata_rename=False,
        preserve_all_audio=args.preserve_all_audio,
    )


if __name__ == "__main__":
    main()
