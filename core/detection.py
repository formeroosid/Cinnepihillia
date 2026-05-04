import subprocess
import json
import logging

log = logging.getLogger(__name__)


def detect_audio_tracks(mkv_path):
    """Probe audio streams and return list of track metadata dicts."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,channels:stream_tags=language",
        "-of", "json", mkv_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    probe = json.loads(result.stdout)
    tracks = []
    for stream in probe.get("streams", []):
        tracks.append({
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "channels": stream.get("channels"),
            "language": stream.get("tags", {}).get("language", "und"),
        })
    return tracks


def build_audio_args(audio_tracks):
    """Build HandBrakeCLI audio arguments from detected tracks."""
    indices = [str(track["index"]) for track in audio_tracks]
    encoders = []
    copy_mask = set()
    fallback_needed = False

    for track in audio_tracks:
        c = track.get("codec_name", track.get("codec", ""))
        if c == "truehd":
            encoders.append("copy:truehd")
            copy_mask.add("truehd")
        elif c in ("ac3", "eac3"):
            encoders.append("copy:ac3")
            copy_mask.add("ac3")
        elif c == "dts":
            encoders.append("copy:dts")
            copy_mask.add("dts")
        else:
            encoders.append("av_aac")
            fallback_needed = True

    audio_args = [
        "-a", ",".join(indices),
        "-E", ",".join(encoders),
        "--audio-copy-mask", ",".join(copy_mask),
    ]
    if fallback_needed:
        audio_args += ["--audio-fallback", "av_aac"]
    return audio_args
