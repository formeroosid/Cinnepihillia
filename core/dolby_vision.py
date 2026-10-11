# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""
Dolby Vision RPU extraction helpers.

Cinnephillia's UHD profile can preserve Dolby Vision metadata across a
software x265 re-encode by:

1. Extracting the DV RPU (dynamic per-scene metadata) from the source
   with ``dovi_tool``, optionally converting it to Profile 8.1 for
   broad player compatibility (Zidoo / Denon / Sony chain).
2. Encoding the video as ordinary HDR10 with ffmpeg/libx265.
3. Injecting the RPU into the finished HEVC bitstream with
   ``dovi_tool inject-rpu`` and remuxing with ``mkvmerge``, which writes
   the Matroska Dolby Vision configuration record.
4. Verifying with ffprobe that the final file actually reports Dolby
   Vision Profile 8.

Why not ``-x265-params dolby-vision-rpu=...``: that option is handled by
the standalone x265 CLI, not by ``x265_param_parse()``. Through ffmpeg's
libx265 wrapper it is rejected with ``Unknown option: dolby-vision-rpu``
as a warning only, so the encode "succeeds" as HDR10. That is what
happened to the Matrix and Project Hail Mary acceptance encodes.

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
import re
import shlex
import shutil
import subprocess

from core.media_analyzer import detect_dolby_vision

log = logging.getLogger(__name__)


class DolbyVisionError(RuntimeError):
    """Raised when a requested DV operation cannot be completed."""


def dovi_tool_available():
    """Return True if ``dovi_tool`` is on PATH."""
    return shutil.which("dovi_tool") is not None


def mkvmerge_available():
    """Return True if ``mkvmerge`` (MKVToolNix) is on PATH."""
    return shutil.which("mkvmerge") is not None


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


def _quote(cmd):
    return " ".join(shlex.quote(str(c)) for c in cmd)


def _run_checked(cmd, what, ok_codes=(0,)):
    """Run ``cmd``; raise DolbyVisionError with stderr on a bad exit code."""
    log.info("DV %s: %s", what, _quote(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in ok_codes:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise DolbyVisionError(f"{what} failed (rc={proc.returncode}): {detail}")
    return proc


def rpu_frame_count(rpu_path):
    """Return the frame count reported by ``dovi_tool info --summary``."""
    proc = _run_checked(
        ["dovi_tool", "info", "-i", rpu_path, "--summary"], "RPU summary",
    )
    m = re.search(r"Frames:\s*(\d+)", proc.stdout)
    if not m:
        raise DolbyVisionError(
            f"could not read frame count from dovi_tool summary: {proc.stdout.strip()}"
        )
    return int(m.group(1))


def video_frame_count(path):
    """Return the number of video packets (frames) in stream v:0 of ``path``."""
    proc = _run_checked(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path],
        "frame count",
    )
    try:
        return int(proc.stdout.strip().splitlines()[0])
    except (IndexError, ValueError):
        raise DolbyVisionError(f"could not parse frame count for {path}: {proc.stdout!r}")


def video_frame_rate(path):
    """Return stream v:0's r_frame_rate as ``num/den`` (e.g. ``24000/1001``)."""
    proc = _run_checked(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path],
        "frame rate",
    )
    rate = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
    if not re.fullmatch(r"\d+/\d+", rate) or rate.endswith("/0"):
        raise DolbyVisionError(f"unusable frame rate {rate!r} for {path}")
    return rate


def apply_dolby_vision(encoded_mkv, rpu_path, output_file, scratch_dir,
                       dry_run=False):
    """
    Inject ``rpu_path`` into the HDR10 video of ``encoded_mkv`` and write
    ``output_file`` with every other track, tag, and chapter carried over
    from ``encoded_mkv`` unchanged.

    Steps: extract HEVC -> compare frame counts -> dovi_tool inject-rpu ->
    mkvmerge remux -> ffprobe verification (Dolby Vision Profile 8).

    Raises DolbyVisionError on any failure. The caller decides what to do
    with ``scratch_dir`` (it is kept on failure so the HDR10 encode is not
    lost).
    """
    base_hevc = os.path.join(scratch_dir, "video.hevc")
    dv_hevc = os.path.join(scratch_dir, "video_dv.hevc")

    extract_cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", encoded_mkv, "-map", "0:v:0", "-c:v", "copy",
        "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", base_hevc,
    ]
    inject_cmd = [
        "dovi_tool", "inject-rpu", "-i", base_hevc, "--rpu-in", rpu_path,
        "-o", dv_hevc,
    ]

    if dry_run:
        log.info("DV extract encoded HEVC: %s", _quote(extract_cmd))
        log.info("DV inject: %s", _quote(inject_cmd))
        log.info("DV remux: mkvmerge -o %s --default-duration 0:<fps>p "
                 "%s --no-video %s", shlex.quote(output_file),
                 shlex.quote(dv_hevc), shlex.quote(encoded_mkv))
        log.info("--dry-run: skipping Dolby Vision injection")
        return output_file

    rpu_frames = rpu_frame_count(rpu_path)
    enc_frames = video_frame_count(encoded_mkv)
    if rpu_frames != enc_frames:
        raise DolbyVisionError(
            f"frame count mismatch: RPU has {rpu_frames} frames, encode has "
            f"{enc_frames}; refusing to inject misaligned metadata"
        )
    log.info("DV frame counts match (%d)", enc_frames)

    fps = video_frame_rate(encoded_mkv)

    _run_checked(extract_cmd, "extract encoded HEVC")
    _run_checked(inject_cmd, "inject-rpu")
    try:
        os.remove(base_hevc)  # ~stream-size of video; free it before remux
    except OSError:
        pass

    remux_cmd = [
        "mkvmerge", "-q", "-o", output_file,
        "--default-duration", f"0:{fps}p",
        "--default-track-flag", "0:yes",
        dv_hevc,
        "--no-video", encoded_mkv,
    ]
    # mkvmerge: 0 = ok, 1 = ok with warnings, 2 = error.
    _run_checked(remux_cmd, "mkvmerge remux", ok_codes=(0, 1))

    dv = detect_dolby_vision(output_file)
    if not dv["present"] or dv.get("profile") != 8:
        raise DolbyVisionError(
            f"output verification failed: expected Dolby Vision Profile 8 in "
            f"{output_file}, ffprobe reported {dv}"
        )
    log.info("DV verified: %s reports Dolby Vision Profile %s",
             output_file, dv.get("profile"))
    return output_file
