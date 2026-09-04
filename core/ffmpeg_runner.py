# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import os
import subprocess
import logging
import shlex
import tempfile

from core.media_analyzer import detect_dolby_vision
from core.dolby_vision import (
    DolbyVisionError, dovi_tool_available, extract_rpu, x265_params_for_rpu,
)

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

def _select_primary_audio(audio_streams):
    """
    Per MakeMKV ordering, the first audio stream in ffprobe order is the
    primary track.

    Returns the audio-relative position (0 for the first audio track),
    suitable for use with ffmpeg's ``0:a:<N>`` selector. Previously this
    returned ffprobe's ``stream=index`` (the absolute container index),
    which the caller then passed to ``0:a:<idx>`` — causing MakeMKV rips
    whose primary audio sat at container index 1 (video at 0) to select
    the *second* audio track instead of the first.
    """
    return 0 if audio_streams else None

def _select_first_english_sub(sub_streams):
    """
    Return index of first English (or untagged) subtitle stream, or None.
    """
    for s in sub_streams:
        if s["language"] in ("eng", "") or not s["language"]:
            return s["index"]
    return None

def _normalize_language_tag(lang, fallback="eng"):
    if not lang:
        return fallback
    lang = lang.strip().lower()
    if lang in ("und", "unknown", "unk"):
        return fallback
    return lang


def _plan_dolby_vision(src, profile, dolby_vision):
    """
    Decide whether to preserve DV for this encode.

    Returns a dict {'enabled': bool, 'target_profile': str|None,
    'source_profile': int|None}. Callers use ``enabled`` to gate the
    RPU extraction and x265-params injection.

    Rules:
        - Only the UHD profile (name == '4k') ever preserves DV.
        - dolby_vision='off': always disabled.
        - dolby_vision='auto': enabled iff source has DV and dovi_tool
          is on PATH; otherwise silently disabled.
        - dolby_vision='p81'/'p76': force enabled; raise if source has
          no DV or dovi_tool is missing.
    """
    if dolby_vision == "off" or profile.get("name") != "4k":
        return {"enabled": False, "target_profile": None, "source_profile": None}

    dv = detect_dolby_vision(src)
    src_profile = dv.get("profile")

    if dolby_vision == "auto":
        if not dv["present"]:
            log.info("Dolby Vision: source has no DV RPU; encoding HDR10 only.")
            return {"enabled": False, "target_profile": None, "source_profile": None}
        if not dovi_tool_available():
            log.warning(
                "Dolby Vision: source has DV Profile %s but dovi_tool is not "
                "on PATH; falling back to HDR10-only. Install dovi_tool to "
                "preserve DV, or pass --dolby-vision off to silence this.",
                src_profile,
            )
            return {"enabled": False, "target_profile": None, "source_profile": src_profile}
        log.info("Dolby Vision: source has DV Profile %s; will re-inject as P8.1.", src_profile)
        return {"enabled": True, "target_profile": "p81", "source_profile": src_profile}

    # Forced modes: p81 / p76
    if not dv["present"]:
        raise DolbyVisionError(
            f"--dolby-vision {dolby_vision} requested but source has no DV RPU: {src}"
        )
    if not dovi_tool_available():
        raise DolbyVisionError(
            f"--dolby-vision {dolby_vision} requested but dovi_tool is not on PATH"
        )
    log.info("Dolby Vision: forced %s; source DV Profile %s.", dolby_vision, src_profile)
    return {"enabled": True, "target_profile": dolby_vision, "source_profile": src_profile}


def _merge_x265_params(video_args, extra):
    """
    Return a new video_args list with ``extra`` appended to the existing
    ``-x265-params`` value (joining with ``:``). If no ``-x265-params``
    flag is present, one is added.

    Kept as a pure function so it can be unit-tested without ffmpeg.
    """
    if not extra:
        return list(video_args)
    out = list(video_args)
    for i, arg in enumerate(out):
        if arg == "-x265-params" and i + 1 < len(out):
            out[i + 1] = f"{out[i + 1]}:{extra}" if out[i + 1] else extra
            return out
    return out + ["-x265-params", extra]


def _cleanup_dv_tmp(tmpdir):
    """Best-effort removal of a DV scratch directory."""
    if not tmpdir:
        return
    try:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        os.rmdir(tmpdir)
    except OSError as e:
        log.debug("DV tmpdir cleanup failed for %s: %s", tmpdir, e)


def encode_with_profile(src, output_file, profile, preserve_all_audio=False,
                        dolby_vision="auto", dry_run=False):
    """
    Run ffmpeg with the given profile dict (from ffmpeg_profiles/select_preset).

    Expected profile shape:
        {
            "name": "bluray" | "4k" | "sd",
            "video_args": [...],
            "input_args": [...],   # optional, placed before -i
        }

    dolby_vision: 'auto' | 'off' | 'p81' | 'p76'. Only affects the UHD
    profile. See ``_plan_dolby_vision`` for full semantics.

    dry_run: log every command without executing.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    audio_streams = _run_ffprobe_streams(src, "a")
    sub_streams = _run_ffprobe_streams(src, "s")

    if not audio_streams:
        log.error(f"No audio streams found in {src}")
        return subprocess.CompletedProcess(args=[], returncode=1)

    sub_idx = _select_first_english_sub(sub_streams)

    dv_plan = _plan_dolby_vision(src, profile, dolby_vision)
    dv_rpu_path = None
    dv_tmpdir = None
    if dv_plan["enabled"]:
        dv_tmpdir = tempfile.mkdtemp(prefix="cinne-dv-")
        dv_rpu_path = os.path.join(dv_tmpdir, "rpu.bin")
        try:
            extract_rpu(src, dv_rpu_path,
                        target_profile=dv_plan["target_profile"],
                        dry_run=dry_run)
        except DolbyVisionError:
            _cleanup_dv_tmp(dv_tmpdir)
            raise

    input_args = profile.get("input_args", [])
    map_args = ["-map", "0:v:0"]
    audio_metadata_args = []
    if preserve_all_audio:
        for out_pos, s in enumerate(audio_streams):
            map_args += ["-map", f"0:{s['index']}"]

            # Copy per-stream metadata (title, language, etc.) from the
            # corresponding source audio stream so MakeMKV-supplied titles
            # like "Director Commentary" survive into the Plex library.
            # Both sides use audio-relative indexing: out_pos for the output,
            # and out_pos for the input because we map audio streams in source
            # order (audio-0 → audio-0, audio-1 → audio-1, etc.).
            audio_metadata_args += [
                f"-map_metadata:s:a:{out_pos}", f"0:s:a:{out_pos}",
            ]

            # Force language=eng only when the source tag is missing or und;
            # otherwise the source language tag (already copied above) wins.
            src_lang = s.get("language", "")
            if not src_lang or src_lang.lower() in {"und", "unknown", "unk", ""}:
                audio_metadata_args += [
                    f"-metadata:s:a:{out_pos}", "language=eng",
                ]
        log.info(
            "preserve-all-audio: mapping %d audio tracks for %s",
            len(audio_streams), src,
        )
    else:
        audio_rel_pos = _select_primary_audio(audio_streams)
        if audio_rel_pos is None:
            log.error(f"Could not determine audio stream to keep for {src}")
            return subprocess.CompletedProcess(args=[], returncode=1)
        # audio_rel_pos is audio-relative (0 = first audio track); use the
        # matching audio-relative selector so we can never accidentally map
        # a subtitle or a later audio track by feeding an absolute container
        # index into an audio-relative slot.
        map_args += ["-map", f"0:a:{audio_rel_pos}"]

        # Preserve per-stream audio metadata (title, language) from the
        # MakeMKV source so labels like "Surround 5.1" / "Director Commentary"
        # survive into the Plex library. Global metadata is still stripped
        # via -map_metadata -1; this re-attaches per-stream tags for the
        # kept audio track only.
        audio_metadata_args = [
            "-map_metadata:s:a:0", f"0:s:a:{audio_rel_pos}",
        ]

        # Fall back to language=eng only when the source tag is missing or und.
        selected_audio = audio_streams[audio_rel_pos]
        src_lang = selected_audio.get("language", "")
        if not src_lang or src_lang.lower() in {"und", "unknown", "unk", ""}:
            audio_metadata_args += ["-metadata:s:a:0", "language=eng"]

    audio_disposition_args = ["-disposition:a:0", "default"]
    video_disposition_args = ["-disposition:v:0", "default"]

    sub_args = []
    sub_metadata_args = []
    if sub_idx is not None:
        map_args += ["-map", f"0:{sub_idx}"]
        sub_args = ["-c:s", "copy", "-disposition:s:0", "0"]

        selected_sub = next((s for s in sub_streams if s["index"] == sub_idx), None)
        sub_lang = _normalize_language_tag(
            selected_sub.get("language") if selected_sub else None,
            fallback="eng",
        )
        sub_metadata_args = ["-metadata:s:s:0", f"language={sub_lang}"]

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        *input_args,
        "-i",
        src,
        *map_args,
        "-map_metadata",
        "-1",
        "-map_chapters",
        "0",
        *_merge_x265_params(
            profile["video_args"],
            x265_params_for_rpu(dv_rpu_path, dv_plan["target_profile"])
            if dv_plan["enabled"] and dv_rpu_path else None,
        ),
        *video_disposition_args,
        "-c:a",
        "copy",
        *audio_metadata_args,
        *audio_disposition_args,
        *sub_args,
        *sub_metadata_args,
        "-max_muxing_queue_size",
        "9999",
        output_file,
    ]

    log.info(f"FFmpeg CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    if dry_run:
        log.info("--dry-run: skipping ffmpeg execution for %s", output_file)
        _cleanup_dv_tmp(dv_tmpdir)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    try:
        result = subprocess.run(cmd, text=True)
    finally:
        _cleanup_dv_tmp(dv_tmpdir)

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

def encode_extra(src, output_file, preset_name, preserve_all_audio=False,
                 dolby_vision="auto", dry_run=False):
    """
    Extras encode — same function name, now ffmpeg-based.
    Currently just uses the BluRay/HD profile; preset_name kept for logging.

    dolby_vision/dry_run are accepted for signature parity with the main
    feature; extras use the BluRay profile so DV is never engaged.
    """
    from core.ffmpeg_profiles import _bluray_profile  # local import to avoid cycles

    log.info(f"Encoding extra with preset '{preset_name}' (mapped to BluRay profile).")
    profile = _bluray_profile()
    return encode_with_profile(src, output_file, profile,
                               preserve_all_audio=preserve_all_audio,
                               dolby_vision=dolby_vision,
                               dry_run=dry_run)