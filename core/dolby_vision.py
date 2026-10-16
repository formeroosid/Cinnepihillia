# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Post-encode Dolby Vision injection with Matroska HDR metadata preservation.

Profile 7 RPU metadata is converted to Profile 8.1 and injected after an
x265 or NVENC encode. Enhancement-layer preservation is not supported.
Static HDR properties are copied to the final Matroska video track; this
does not insert static HDR SEI messages into the elementary HEVC stream.
"""

import json
import logging
import math
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
    return shutil.which("dovi_tool") is not None


def mkvmerge_available():
    return shutil.which("mkvmerge") is not None


def extract_rpu(src, rpu_out, target_profile="p81", dry_run=False):
    """Extract the source RPU, converting it to Profile 8.1 with mode 2."""
    if not dovi_tool_available():
        raise DolbyVisionError(
            "dovi_tool not found on PATH; install it to preserve Dolby Vision "
            "or pass --dolby-vision off to skip DV preservation."
        )
    if target_profile == "p76":
        log.warning("Profile 7 preservation is unsupported; extracting as P8.1.")
    ffmpeg_cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", src, "-map", "0:v:0", "-c:v", "copy",
        "-bsf:v", "hevc_mp4toannexb", "-f", "hevc", "-",
    ]
    dovi_cmd = ["dovi_tool", "-m", "2", "extract-rpu", "-", "-o", rpu_out]
    log.info("DV extract (ffmpeg): %s", _quote(ffmpeg_cmd))
    log.info("DV extract (dovi_tool): %s", _quote(dovi_cmd))
    if dry_run:
        log.info("--dry-run: skipping actual DV RPU extraction")
        return rpu_out
    os.makedirs(os.path.dirname(rpu_out) or ".", exist_ok=True)
    with subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE) as ff:
        proc = subprocess.run(dovi_cmd, stdin=ff.stdout,
                              capture_output=True, text=True)
        ff.stdout.close()
        ff.wait()
    if ff.returncode != 0 or proc.returncode != 0 or not os.path.isfile(rpu_out):
        raise DolbyVisionError(
            f"RPU extraction failed (ffmpeg={ff.returncode}, "
            f"dovi_tool={proc.returncode}): {(proc.stderr or '').strip()}"
        )
    log.info("DV RPU extracted to %s (%d bytes)", rpu_out, os.path.getsize(rpu_out))
    return rpu_out


def _quote(cmd):
    return " ".join(shlex.quote(str(c)) for c in cmd)


def _run_checked(cmd, what, ok_codes=(0,)):
    log.info("DV %s: %s", what, _quote(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in ok_codes:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise DolbyVisionError(f"{what} failed (rc={proc.returncode}): {detail}")
    return proc


def rpu_frame_count(rpu_path):
    proc = _run_checked(
        ["dovi_tool", "info", "-i", rpu_path, "--summary"], "RPU summary")
    m = re.search(r"Frames:\s*(\d+)", proc.stdout)
    if not m or int(m.group(1)) <= 0:
        raise DolbyVisionError(f"could not read positive RPU frame count: {proc.stdout!r}")
    return int(m.group(1))


def _probe_video_field(path, field, count_packets=False):
    """Read one primary-video field from structured ffprobe output."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if count_packets:
        cmd.append("-count_packets")
    cmd += ["-show_entries", f"stream={field}", "-of", "json", path]
    proc = _run_checked(cmd, f"probe {field}")
    try:
        streams = json.loads(proc.stdout)["streams"]
        if not isinstance(streams, list) or len(streams) != 1:
            raise ValueError("expected exactly one selected video stream")
        value = streams[0][field]
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("expected a string or integer field")
        return str(value)
    except (ValueError, KeyError, TypeError) as exc:
        raise DolbyVisionError(f"could not read {field} for {path}: {proc.stdout!r}") from exc


def video_frame_count(path):
    value = _probe_video_field(path, "nb_read_packets", count_packets=True)
    if not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise DolbyVisionError(f"unusable video packet count {value!r} for {path}")
    return int(value)


def video_frame_rate(path):
    rate = _probe_video_field(path, "r_frame_rate")
    if not re.fullmatch(r"[0-9]+/[0-9]+", rate):
        raise DolbyVisionError(f"unusable frame rate {rate!r} for {path}")
    numerator, denominator = map(int, rate.split("/"))
    if numerator <= 0 or denominator <= 0:
        raise DolbyVisionError(f"unusable frame rate {rate!r} for {path}")
    return rate


# mkvmerge identification property -> CLI option, component count, integer flag.
_HDR_FIELDS = {
    "color_matrix_coefficients": ("--colour-matrix", 1, True),
    "color_range": ("--colour-range", 1, True),
    "color_transfer_characteristics": ("--colour-transfer-characteristics", 1, True),
    "color_primaries": ("--colour-primaries", 1, True),
    "chromaticity_coordinates": ("--chromaticity-coordinates", 6, False),
    "white_color_coordinates": ("--white-colour-coordinates", 2, False),
    "min_luminance": ("--min-luminance", 1, False),
    "max_luminance": ("--max-luminance", 1, False),
    "max_content_light": ("--max-content-light", 1, True),
    "max_frame_light": ("--max-frame-light", 1, True),
}


def _hdr_values(key, value):
    """Validate known MKVToolNix numeric properties; never invent defaults."""
    _, count, integer = _HDR_FIELDS[key]
    parts = value.split(",") if isinstance(value, str) else [value]
    try:
        if len(parts) != count or any(isinstance(v, bool) for v in parts):
            raise ValueError("invalid component count/type")
        values = tuple(float(v) for v in parts)
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("expected finite nonnegative values")
        if integer and any(not v.is_integer() for v in values):
            raise ValueError("expected integers")
        if count > 1 and any(v > 1 for v in values):
            raise ValueError("chromaticity coordinates must be between 0 and 1")
        return tuple(int(v) for v in values) if integer else values
    except (TypeError, ValueError, OverflowError) as exc:
        raise DolbyVisionError(f"invalid HDR property {key}={value!r}") from exc


def read_hdr_properties(path):
    """Read the first video track's container HDR/color properties."""
    proc = _run_checked(["mkvmerge", "-J", path], "HDR identification", ok_codes=(0, 1))
    try:
        data = json.loads(proc.stdout)
        if not isinstance(data, dict):
            raise ValueError("expected an identification object")
        if data.get("errors"):
            raise ValueError(str(data["errors"]))
        tracks = data["tracks"]
        if not isinstance(tracks, list):
            raise ValueError("expected a track list")
        video = next(t for t in tracks if t["type"] == "video")
        properties = video.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("expected video properties")
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        raise DolbyVisionError(f"could not identify video HDR properties for {path}") from exc
    result = {key: _hdr_values(key, properties[key])
              for key in _HDR_FIELDS if key in properties}
    if "min_luminance" in result and "max_luminance" in result:
        if result["min_luminance"][0] > result["max_luminance"][0]:
            raise DolbyVisionError("minimum mastering luminance exceeds maximum")
    return result


def hdr_remux_args(properties):
    """Options apply to track 0 of the following raw HEVC input."""
    args = []
    for key, values in properties.items():
        option, _, integer = _HDR_FIELDS[key]
        text = ",".join(str(v) if integer else
                        format(v, ".12f").rstrip("0").rstrip(".") for v in values)
        args += [option, f"0:{text}"]
    return args


def verify_hdr_properties(path, expected):
    """Fail if a copied property disappeared or materially changed."""
    if not expected:
        return
    actual = read_hdr_properties(path)
    for key, values in expected.items():
        other = actual.get(key)
        integer = _HDR_FIELDS[key][2]
        if other is None or len(other) != len(values) or any(
            a != b if integer else not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-7)
            for a, b in zip(values, other)
        ):
            raise DolbyVisionError(
                f"HDR verification failed for {key}: expected {values}, got {other}")
    log.info("HDR container properties verified (%d fields)", len(expected))


def apply_dolby_vision(encoded_mkv, rpu_path, output_file, scratch_dir,
                       dry_run=False):
    """Inject RPU and preserve HDR container properties, other tracks and chapters."""
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
                 "<HDR options read from encoded MKV> %s --no-video %s",
                 shlex.quote(output_file), shlex.quote(dv_hevc), shlex.quote(encoded_mkv))
        log.info("--dry-run: skipping injection and HDR identification/verification")
        return output_file

    rpu_frames = rpu_frame_count(rpu_path)
    enc_frames = video_frame_count(encoded_mkv)
    if rpu_frames != enc_frames:
        raise DolbyVisionError(
            f"frame count mismatch: RPU has {rpu_frames} frames, encode has "
            f"{enc_frames}; refusing to inject misaligned metadata")
    log.info("DV frame counts match (%d)", enc_frames)
    fps = video_frame_rate(encoded_mkv)
    hdr = read_hdr_properties(encoded_mkv)
    log.info("Preserving HDR/color container properties: %s", hdr)

    _run_checked(extract_cmd, "extract encoded HEVC")
    _run_checked(inject_cmd, "inject-rpu")
    try:
        os.remove(base_hevc)
    except OSError:
        pass
    remux_cmd = [
        "mkvmerge", "-q", "-o", output_file,
        "--default-duration", f"0:{fps}p",
        "--default-track-flag", "0:yes",
        *hdr_remux_args(hdr), dv_hevc,
        "--no-video", encoded_mkv,
    ]
    _run_checked(remux_cmd, "mkvmerge remux", ok_codes=(0, 1))
    dv = detect_dolby_vision(output_file)
    if not dv["present"] or dv.get("profile") != 8:
        raise DolbyVisionError(
            f"output verification failed: expected Dolby Vision Profile 8 in "
            f"{output_file}, ffprobe reported {dv}")
    verify_hdr_properties(output_file, hdr)
    log.info("DV verified: %s reports Dolby Vision Profile %s",
             output_file, dv.get("profile"))
    return output_file
