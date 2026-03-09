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


def rename_with_amc(input_dir, output_root,
                    series_format="{n}/Season {s}/{n} - {s00e00} - {t}",
                    action="duplicate", dry_run=False,
                    plex_host=None, exclude_list=None):
    """Use AMC script for full automation including optional Plex notification."""
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
    ]
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
