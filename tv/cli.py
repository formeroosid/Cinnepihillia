import argparse
from pathlib import Path

from shared.logging_config import setup_logging
from tv.tv_pipeline import process_tv_series
from tv.inventory import inventory_report, print_inventory


def main():
    parser = argparse.ArgumentParser(description="Cinephillia TV Processor")
    sub = parser.add_subparsers(dest="command")

    # --- process ---
    proc = sub.add_parser("process", help="Encode and organise a TV series")
    proc.add_argument("--input", required=True, type=Path)
    proc.add_argument("--staging", required=True, type=Path)
    proc.add_argument("--output", required=True, type=Path)
    proc.add_argument("--series", required=True)
    proc.add_argument("--duration-min", type=int, default=2400)
    proc.add_argument("--duration-max", type=int, default=5400)
    proc.add_argument("--plex-host", default=None)
    proc.add_argument("--dry-run", action="store_true")
    proc.add_argument("--encode", choices=["4k", "bluray", "dvd", "sd"], default=None,
                      help="Override automatic profile detection (4k, bluray, dvd, sd)")

    # --- inventory ---
    inv = sub.add_parser("inventory", help="Check collection against TVDB")
    inv.add_argument("--series", required=True)
    inv.add_argument("--plex-dir", type=Path, default=None)
    inv.add_argument("--input", type=Path, default=None)
    inv.add_argument("--duration-min", type=int, default=2400)
    inv.add_argument("--duration-max", type=int, default=5400)

    args = parser.parse_args()
    setup_logging()

    if args.command == "process":
        process_tv_series(
            input_root=args.input,
            staging_dir=args.staging,
            output_root=args.output,
            series_name=args.series,
            duration_min=args.duration_min,
            duration_max=args.duration_max,
            plex_host=args.plex_host,
            encode_profile=args.encode,
            dry_run=args.dry_run,
        )
    elif args.command == "inventory":
        if args.plex_dir:
            report = inventory_report(args.series, plex_series_root=args.plex_dir)
        elif args.input:
            from tv.disc_parser import parse_tv_input
            from tv.episode_classifier import classify_titles
            titles = parse_tv_input(args.input)
            episodes, _ = classify_titles(
                titles, (args.duration_min, args.duration_max))
            report = inventory_report(args.series, ripped_episodes=episodes)
        else:
            report = inventory_report(args.series)
        print_inventory(report)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
