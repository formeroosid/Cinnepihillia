# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import subprocess
import json
import logging

log = logging.getLogger(__name__)


def detect_resolution(mkv_path):
    """Return (width, height) of the first video stream."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", mkv_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        probe = json.loads(result.stdout)
        stream = probe["streams"][0]
        return stream["width"], stream["height"]
    except Exception as e:
        log.error(f"ffprobe failed for {mkv_path}: {e}")
        return None, None


def get_duration(mkv_path):
    """Return duration in seconds of the file."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", mkv_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        probe = json.loads(result.stdout)
        return float(probe["format"]["duration"])
    except Exception as e:
        log.error(f"ffprobe duration failed for {mkv_path}: {e}")
        return 0.0


def detect_dolby_vision(mkv_path):
    """
    Detect Dolby Vision on the primary video stream.

    Returns a dict:
        {"present": bool, "profile": int|None, "bl_present": bool,
         "el_present": bool, "rpu_present": bool}

    Uses ffprobe's ``stream_side_data_list`` which exposes the
    ``DOVI configuration record`` side-data type on DV-carrying HEVC
    streams. When absent (or on any parse error), returns present=False
    so callers can fall through to plain HDR10.
    """
    empty = {
        "present": False, "profile": None,
        "bl_present": False, "el_present": False, "rpu_present": False,
    }
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream_side_data=side_data_type,dv_profile,"
                             "dv_level,rpu_present_flag,el_present_flag,"
                             "bl_present_flag",
            "-of", "json", mkv_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return empty
        probe = json.loads(result.stdout or "{}")
        for stream in probe.get("streams", []):
            for sd in stream.get("side_data_list", []) or []:
                sd_type = (sd.get("side_data_type") or "").lower()
                if "dovi" in sd_type or "dolby vision" in sd_type:
                    return {
                        "present": True,
                        "profile": sd.get("dv_profile"),
                        "bl_present": bool(sd.get("bl_present_flag", 0)),
                        "el_present": bool(sd.get("el_present_flag", 0)),
                        "rpu_present": bool(sd.get("rpu_present_flag", 0)),
                    }
        return empty
    except Exception as e:
        log.warning(f"Dolby Vision probe failed for {mkv_path}: {e}")
        return empty
