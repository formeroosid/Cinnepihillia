# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""
Dolby Vision RPU extraction helpers.

Cinnephillia's UHD profile can preserve Dolby Vision metadata across a
software x265 re-encode by:

1. Extracting the DV RPU (dynamic per-scene metadata) from the source
   with ``dovi_tool``, optionally converting it to Profile 8.1 for
   broad player compatibility (Zidoo / Denon / Sony chain).
2. Passing the extracted RPU to libx265 via ``dolby-vision-rpu=<path>``
   and ``dolby-vision-profile=<n>`` in ``-x265-params``.

Profile choices:
    - ``p81`` (default for ``auto``): P8.1, single-layer, HDR10-compatible.
      This is what the Zidoo Z9X / Z2000 chain prefers and what most
      modern displays negotiate cleanly.
    - ``p76``: dual-layer P7 preservation. Requires the source to already
      be P7 dual-layer (BL+EL+RPU) and produces a much larger output.
      Not currently supported here — kept as a documented CLI value for
      forward compatibility. Falls back to P8.1 with a warning.
"""

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)


class DolbyVisionError(RuntimeError):
    """Raised when a requested DV operation cannot be completed."""


def dovi_tool_available():
    """Return True if ``dovi_tool`` is on PATH."""
    return shutil.which("dovi_tool") is not None


def extract_rpu(src, rpu_out, target_profile="p81", dry_run=False):
    """
    Extract the Dolby Vision RPU from ``src`` to ``rpu_out``.

    target_profile:
        ``p81`` — convert to Profile 8.1 during extraction (mode 2).
        ``p76`` — preserve as-is (not fully supported end-to-end; the
                  encode side currently emits P8.1 regardless, so this
                  logs a warning and behaves like p81).

    Returns the path to the extracted RPU on success. Raises
    ``DolbyVisionError`` on failure. When ``dry_run`` is True, only the
    command is logged and ``rpu_out`` is returned without invoking
    ``dovi_tool``.
    """
    if not dovi_tool_available():
        raise DolbyVisionError(
            "dovi_tool not found on PATH; install it to preserve Dolby Vision "
            "or pass --dolby-vision off to skip DV preservation."
        )

    if target_profile == "p76":
        log.warning(
            "Dolby Vision Profile 7.6 preservation is not yet supported "
            "end-to-end; extracting as P8.1 instead."
        )
        target_profile = "p81"

    # dovi_tool extract-rpu reads HEVC from stdin, so we pipe the video
    # stream out of ffmpeg first. Using -c:v copy + hevc_mp4toannexb
    # avoids re-decoding.
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", src,
        "-map", "0:v:0", "-c:v", "copy",
        "-bsf:v", "hevc_mp4toannexb",
        "-f", "hevc", "-",
    ]
    # dovi_tool mode 2 rewrites the RPU as Profile 8.1 during extract.
    dovi_cmd = [
        "dovi_tool", "-m", "2", "extract-rpu", "-", "-o", rpu_out,
    ]

    log.info("DV extract (ffmpeg): %s", " ".join(ffmpeg_cmd))
    log.info("DV extract (dovi_tool): %s", " ".join(dovi_cmd))

    if dry_run:
        log.info("--dry-run: skipping actual DV RPU extraction")
        return rpu_out

    os.makedirs(os.path.dirname(rpu_out) or ".", exist_ok=True)
    with subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE) as ff:
        proc = subprocess.run(
            dovi_cmd, stdin=ff.stdout, capture_output=True, text=True,
        )
        ff.stdout.close()
        ff.wait()

    if proc.returncode != 0 or not os.path.isfile(rpu_out):
        stderr = proc.stderr.strip() if proc.stderr else ""
        raise DolbyVisionError(
            f"dovi_tool extract-rpu failed (rc={proc.returncode}): {stderr}"
        )

    size = os.path.getsize(rpu_out)
    log.info("DV RPU extracted to %s (%d bytes)", rpu_out, size)
    return rpu_out


def x265_params_for_rpu(rpu_path, profile="p81"):
    """
    Return the ``:``-joined x265-params fragment for DV re-injection.

    Callers should append this to the existing ``-x265-params`` string
    already emitted by the UHD profile.
    """
    if profile != "p81":
        profile = "p81"  # see extract_rpu() — only P8.1 is fully wired.
    # dolby-vision-profile 8.1 maps to x265's integer profile id 81.
    return f"dolby-vision-rpu={rpu_path}:dolby-vision-profile=81:vbv-bufsize=160000:vbv-maxrate=160000"
