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
    parser.add_argument("--type", choices=["movie", "tv"], default="movie",
                        help="Content type: movie or tv.")
    parser.add_argument("--series-name", default=None,
                        help="Optional TV series name (defaults to folder name).")
    parser.add_argument(
        "--preserve-all-audio", action="store_true",
        help="Losslessly copy every audio track; default: keep only the primary track.",
    )
    parser.add_argument(
        "--dolby-vision", choices=["auto", "off", "p81", "p76"], default="auto",
        help="Movie/TV UHD Dolby Vision handling. auto preserves DV as P8.1 when "
             "source metadata and dovi_tool/mkvmerge are available. off disables it; "
             "p81/p76 require source DV and both tools. p76 currently converts to P8.1. "
             "Only applies to newly encoded UHD profiles; existing TV staging files are skipped.",
    )
    parser.add_argument(
        "--encoder", choices=["native", "nvenc"], default="native",
        help="Movie/TV video backend. native uses x265 for HD/UHD and VAAPI for SD. "
             "nvenc uses NVIDIA HEVC on GPU 0. Existing TV staging files are skipped.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Movies: preview processing commands. TV: input inventory only, "
             "without encoder preflight or Dolby Vision planning.",
    )
    args = parser.parse_args()
    setup_logging()
    root = Path(args.path)
    if args.type == "movie":
        process_movie(str(root), args.mode,
                      preserve_all_audio=args.preserve_all_audio,
                      dolby_vision=args.dolby_vision, dry_run=args.dry_run,
                      encoder=args.encoder)
        return
    process_tv_series(
        input_root=str(root / "rip"),
        staging_dir=str(root / "process" / "staging"),
        output_root=str(root / "Plex Movie Files"),
        series_name=args.series_name or root.name,
        duration_min=None, duration_max=None, plex_host=None,
        encode_profile=None, dry_run=args.dry_run, expected_counts=None,
        use_metadata_rename=False, preserve_all_audio=args.preserve_all_audio,
        encoder=args.encoder, dolby_vision=args.dolby_vision,
    )


if __name__ == "__main__":
    main()
