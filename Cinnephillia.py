#!/usr/bin/env python3
"""
Cinnephillia — Movie & TV processing entry point.

Thin wrapper that delegates to:
  - cinephillia.movies.movie_pipeline.process_movie
  - cinephillia.tv.tv_pipeline.process_tv_series
"""
import argparse
from pathlib import Path

from shared.logging_config import setup_logging
from movies.movie_pipeline import process_movie
from tv.tv_pipeline import process_tv_series


def main():
    parser = argparse.ArgumentParser(description="Cinnephillia media processor")
    parser.add_argument(
        "path",
        help="Path to Movie Title (YYYY) or TV series root",
    )
    parser.add_argument(
        "--mode",
        choices=["feature", "extras", "both"],
        default="both",
        help="Process main feature, extras, or both (movie mode only).",
    )
    parser.add_argument(
        "--type",
        choices=["movie", "tv"],
        default="movie",
        help="Content type: movie or tv.",
    )
    parser.add_argument(
        "--series-name",
        help="Optional override for TV series name (defaults to folder name).",
    )
    args = parser.parse_args()

    setup_logging()

    root = Path(args.path)

    if args.type == "movie":
        process_movie(str(root), args.mode)
        return

    series_name = args.series_name or root.name
    input_root = root / "rip"
    staging_dir = root / "process" / "staging"
    output_root = root / "Plex Movie Files"

    process_tv_series(
        input_root=str(input_root),
        staging_dir=str(staging_dir),
        output_root=str(output_root),
        series_name=series_name,
        duration_min=None,
        duration_max=None,
        plex_host=None,
        encode_profile=None,
        dry_run=False,
        expected_counts=None,
        use_metadata_rename=False,
    )


if __name__ == "__main__":
    main()