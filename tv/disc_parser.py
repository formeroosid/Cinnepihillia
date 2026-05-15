# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import re
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def parse_tv_input(series_root):
    """
    Scan S{season}D{disc} sub-folders for MKV rips.
    Automatically looks inside a 'rip' subdirectory if present.
    Returns a sorted list of dicts with path, season, disc, title_num.
    """
    series_root = Path(series_root)
    rip_dir = series_root / "rip"
    scan_root = rip_dir if rip_dir.is_dir() else series_root

    titles = []
    for disc_dir in sorted(scan_root.iterdir()):
        if not disc_dir.is_dir():
            continue
        match = re.match(r"S(\d+)D(\d+)", disc_dir.name, re.IGNORECASE)
        if not match:
            log.warning(f"Skipping unrecognised folder: {disc_dir.name}")
            continue
        season = int(match.group(1))
        disc = int(match.group(2))
        for mkv in sorted(disc_dir.glob("*.mkv")):
            title_match = re.search(r"_t(\d+)", mkv.name)
            if not title_match:
                log.warning(f"No title number in filename, skipping: {mkv.name}")
                continue
            titles.append({
                "path": mkv,
                "season": season,
                "disc": disc,
                "title_num": int(title_match.group(1)),
            })
    log.info(f"Parsed {len(titles)} MKV titles from {scan_root}")
    return titles
