#!/usr/bin/env python3
"""
Cinnephillia — Movie processing entry point.
Thin wrapper that delegates to cinephillia.movies.movie_pipeline.
"""
import argparse
from cinephillia.shared.logging_config import setup_logging
from cinephillia.movies.movie_pipeline import process_movie


def main():
    parser = argparse.ArgumentParser(description="Handbrake batch script")
    parser.add_argument("path", help="Path to Movie Title (YYYY)")
    parser.add_argument("--mode", choices=["feature", "extras", "both"],
                        default="both",
                        help="Process main feature, extras, or both.")
    args = parser.parse_args()

    setup_logging()
    process_movie(args.path, args.mode)


if __name__ == "__main__":
    main()
