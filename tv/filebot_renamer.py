# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)

FILEBOT_BIN = "filebot"


def rename_with_filebot(input_dir, output_root, db="TheTVDB",
                        series_format="{plex}", action="duplicate",
                        dry_run=False):
    """Direct FileBot rename into Plex structure."""
    cmd = [
        FILEBOT_BIN, "-rename", "-r", str(input_dir),
        "--db", db,
        "-non-strict",
        "--action", "test" if dry_run else action,
        "--output", str(output_root),
        "--format", series_format,
    ]
    log.info(f"FileBot CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
    return result



def rename_with_amc(input_dir, output_root, series_name=None,
                    series_format="{n}/Season {s}/{n} - {s00e00} - {t}",
                    action="duplicate", dry_run=False,
                    plex_host=None, exclude_list=None):
    cmd = [
        FILEBOT_BIN, "-script", "fn:amc",
        str(input_dir),
        "--output", str(output_root),
        "--action", "test" if dry_run else action,
        "--conflict", "skip",
        "-non-strict",
        "--log-file", "amc.log",
        "--def", f"seriesFormat={series_format}",
        "--def", "ut_label=TV",
        "--def", "ut_kind=multi",
        "--def", "music=n",
    ]
    if series_name:
        cmd += ["--def", f"ut_title={series_name}"]
    if plex_host:
        cmd += ["--def", f"plex={plex_host}"]
    if exclude_list:
        cmd += ["--def", f"excludeList={exclude_list}"]

    log.info(f"AMC CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
    return result

def rename_with_query(input_dir, output_root, series_name,
                      db="TheMovieDB::TV",
                      series_format="{n}/Season {s}/{n} - {s00e00} - {t}",
                      action="duplicate", dry_run=False):
    """Direct rename with explicit query - reliable for generic filenames."""
    fmt = f"{output_root}/{series_format}"
    cmd = [
        FILEBOT_BIN, "-rename", "-r", str(input_dir),
        "--db", db,
        "-non-strict",
        "--action", "test" if dry_run else action,
        "--q", series_name,
        "--format", fmt,
    ]
    log.info(f"FileBot CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    log.info(result.stdout)
    if result.returncode != 0:
        log.error(result.stderr)
    return result


def prepare_rename_staging(staging_dir, series_name):
    """Flatten staged files into sequential order for FileBot matching."""
    rename_dir = Path(staging_dir) / "_filebot_stage"
    rename_dir.mkdir(exist_ok=True)

    files = sorted(Path(staging_dir).rglob("*.mkv"))
    # Exclude the _filebot_stage dir itself
    files = [f for f in files if "_filebot_stage" not in str(f)]

    for i, f in enumerate(files, 1):
        link = rename_dir / f"{series_name} - E{i:02d}.mkv"
        if not link.exists():
            link.symlink_to(f)

    return rename_dir