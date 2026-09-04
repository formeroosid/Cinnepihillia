# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

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


def encode_with_profile(src, output_file, profile, preserve_all_audio=False):
    """
    Run ffmpeg with the given profile dict (from ffmpeg_profiles/select_preset).

    Expected profile shape:
        {
            "name": "bluray" | "4k" | "sd",
            "video_args": [...],
            "input_args": [...],   # optional, placed before -i
        }
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    audio_streams = _run_ffprobe_streams(src, "a")
    sub_streams = _run_ffprobe_streams(src, "s")

    if not audio_streams:
        log.error(f"No audio streams found in {src}")
        return subprocess.CompletedProcess(args=[], returncode=1)

    sub_idx = _select_first_english_sub(sub_streams)
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
        # -map_metadata -1 strips the global metadata dictionary, which on
        # MakeMKV rips also contains per-chapter title tags. Re-attach the
        # chapter title metadata so Plex shows "Chapter 01".."Chapter NN"
        # instead of raw timestamps in place of names.
        "-map_metadata:c",
        "0:c",
        "-map_metadata:g:c",
        "0:g:c",
        *profile["video_args"],
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

def encode_extra(src, output_file, preset_name, preserve_all_audio=False):
    """
    Extras encode — same function name, now ffmpeg-based.
    Currently just uses the BluRay/HD profile; preset_name kept for logging.
    """
    from core.ffmpeg_profiles import _bluray_profile  # local import to avoid cycles

    log.info(f"Encoding extra with preset '{preset_name}' (mapped to BluRay profile).")
    profile = _bluray_profile()
    return encode_with_profile(src, output_file, profile, preserve_all_audio=preserve_all_audio)