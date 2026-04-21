import os
import subprocess
import logging
import shlex

log = logging.getLogger(__name__)


def _run_ffprobe_streams(src, stream_type):
    """
    Generic helper to get stream info from ffprobe.
    stream_type: 'a' (audio) or 's' (subtitle).
    Returns list of dicts with keys: index, codec_name, profile, language.
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        stream_type,
        "-show_entries",
        "stream=index,codec_name,profile:stream_tags=language",
        "-of",
        "csv=p=0",
        src,
    ]
    log.debug(f"ffprobe CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"ffprobe failed for {src}: {result.stderr.strip()}")
        return []

    streams = []
    for line in result.stdout.splitlines():
        parts = line.split(",")
        if not parts:
            continue
        idx = parts[0]
        codec = parts[1] if len(parts) > 1 else ""
        profile = parts[2] if len(parts) > 2 else ""
        lang = parts[3] if len(parts) > 3 else ""
        streams.append(
            {
                "index": idx,
                "codec_name": codec,
                "profile": profile,
                "language": lang,
            }
        )
    return streams


def _select_dtshd_like_audio(audio_streams):
    """
    Pick best audio stream with this priority:
      1) DTS-HD MA in English
      2) Any DTS in English
      3) First audio stream
    Returns index as string or None.
    """
    # 1) DTS-HD MA (profile) in English
    for s in audio_streams:
        if s["codec_name"].startswith("dts") and "DTS-HD MA" in s.get("profile", ""):
            if s["language"] in ("eng", "") or not s["language"]:
                return s["index"]

    # 2) Any DTS in English
    for s in audio_streams:
        if s["codec_name"].startswith("dts"):
            if s["language"] in ("eng", "") or not s["language"]:
                return s["index"]

    # 3) Fallback: first audio
    return audio_streams[0]["index"] if audio_streams else None


def _select_first_english_sub(sub_streams):
    """
    Return index of first English (or untagged) subtitle stream, or None.
    """
    for s in sub_streams:
        if s["language"] in ("eng", "") or not s["language"]:
            return s["index"]
    return None


def encode_with_profile(src, output_file, profile, copy_audio_only=True):
    """
    Run ffmpeg with the given profile dict (from ffmpeg_profiles/select_preset).

    - src: input MKV path
    - output_file: output MKV path
    - profile: dict containing at least:
          {
              "name": "bluray" | "4k" | "sd",
              "video_args": [ ... ffmpeg video options ... ]
          }
      where video_args contains only output-side options (filters, codec, rc, qp, profile),
      NOT hwaccel flags.
    - copy_audio_only: kept for compatibility; always copy audio streams.

    Behavior:
      * 1 video stream: 0:v:0
      * ALL audio streams: 0:a
      * First English (or untagged) subtitle, if present
      * Mark "best" audio (DTS-HD / DTS English) as default
    """
    del copy_audio_only  # we always copy all audio streams

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    audio_streams = _run_ffprobe_streams(src, "a")
    sub_streams = _run_ffprobe_streams(src, "s")

    if not audio_streams:
        log.error(f"No audio streams found in {src}")
        return subprocess.CompletedProcess(args=[], returncode=1)

    audio_idx = _select_dtshd_like_audio(audio_streams)
    sub_idx = _select_first_english_sub(sub_streams)

    # --- Build mapping: video + all audio + optional first subtitle ---
    map_args = ["-map", "0:v:0", "-map", "0:a"]  # keep ALL audio tracks

    sub_args = []
    if sub_idx is not None:
        map_args += ["-map", f"0:{sub_idx}"]
        sub_args = ["-c:s", "copy", "-disposition:s:0", "default"]

    # Determine which audio stream becomes default.
    # Because we map "-map 0:a", ffmpeg preserves input audio order, so we
    # find the position of audio_idx in the original list.
    default_audio_pos = 0
    if audio_idx is not None:
        for i, s in enumerate(audio_streams):
            if s["index"] == audio_idx:
                default_audio_pos = i
                break

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        # VAAPI hardware accel (applies to input, so must be before -i)
        "-hwaccel",
        "vaapi",
        "-hwaccel_output_format",
        "vaapi",
        "-vaapi_device",
        "/dev/dri/renderD128",
        "-i",
        src,
        *map_args,
        "-map_metadata",
        "-1",
        *profile["video_args"],
        "-c:a",
        "copy",
        *sub_args,
        # Mark chosen best audio stream as default
        f"-disposition:a:{default_audio_pos}",
        "default",
        "-max_muxing_queue_size",
        "9999",
        output_file,
    ]

    log.info(f"FFmpeg CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    # For long ffmpeg runs, don't capture_output to avoid large-buffer issues.
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        log.error(f"Encode failed (rc={result.returncode}) for {src}")
        if os.path.isfile(output_file):
            os.remove(output_file)
    elif not os.path.isfile(output_file):
        log.error(f"Encode returned success but output file missing: {output_file}")
    elif os.path.getsize(output_file) < 1024:
        log.error(
            f"Suspiciously small output ({os.path.getsize(output_file)} bytes): {output_file}"
        )
    else:
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        log.info(f"Encode succeeded: {output_file} ({size_mb:.1f} MB)")

    return result


def encode_extra(src, output_file, preset_name):
    """
    Extras encode — same function name, now ffmpeg-based.
    Currently just uses the BluRay/HD profile; preset_name kept for logging.
    """
    from .ffmpeg_profiles import _bluray_profile  # local import to avoid cycles

    log.info(f"Encoding extra with preset '{preset_name}' (mapped to BluRay profile).")
    profile = _bluray_profile()
    return encode_with_profile(src, output_file, profile)