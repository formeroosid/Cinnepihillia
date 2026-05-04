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
