# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import argparse
from pathlib import Path

from shared.logging_config import setup_logging
from tv.tv_pipeline import process_tv_series
from tv.inventory import inventory_report, print_inventory


def main():
    parser = argparse.ArgumentParser(description="Cinephillia TV Processor")
    sub = parser.add_subparsers(dest="command")
    proc = sub.add_parser("process", help="Encode and organise a TV series")
    proc.add_argument("--input", required=True, type=Path)
    proc.add_argument("--staging", required=True, type=Path)
    proc.add_argument("--output", required=True, type=Path)
    proc.add_argument("--series", required=True)
    proc.add_argument("--duration-min", type=int, default=2400)
    proc.add_argument("--duration-max", type=int, default=5400)
    proc.add_argument("--plex-host", default=None)
    proc.add_argument("--dry-run", action="store_true",
                      help="Inventory only; no encoder preflight or DV planning.")
    proc.add_argument("--preserve-all-audio", action="store_true",
                      help="Losslessly copy every audio track instead of only the primary.")
    proc.add_argument("--encoder", choices=["native", "nvenc"], default="native",
                      help="Video backend for new encodes; existing staging files are skipped.")
    proc.add_argument("--dolby-vision", choices=["auto", "off", "p81", "p76"], default="auto",
                      help="UHD DV mode: auto, off, or required p81/p76 (p76 converts to P8.1). "
                           "Required modes need source DV, dovi_tool and mkvmerge. "
                           "Existing staging files are not revalidated.")
    proc.add_argument("--encode", choices=["4k", "bluray", "dvd", "sd"], default=None,
                      help="Legacy profile parameter; currently not applied by the TV pipeline.")
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
            input_root=args.input, staging_dir=args.staging, output_root=args.output,
            series_name=args.series, duration_min=args.duration_min,
            duration_max=args.duration_max, plex_host=args.plex_host,
            encode_profile=args.encode, dry_run=args.dry_run,
            preserve_all_audio=args.preserve_all_audio,
            encoder=args.encoder, dolby_vision=args.dolby_vision,
        )
    elif args.command == "inventory":
        if args.plex_dir:
            report = inventory_report(args.series, plex_series_root=args.plex_dir)
        elif args.input:
            from tv.disc_parser import parse_tv_input
            from tv.episode_classifier import classify_titles
            titles = parse_tv_input(args.input)
            episodes, _ = classify_titles(titles, (args.duration_min, args.duration_max))
            report = inventory_report(args.series, ripped_episodes=episodes)
        else:
            report = inventory_report(args.series)
        print_inventory(report)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
