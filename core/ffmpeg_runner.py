# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import os
import subprocess
import logging
import re
import json
import shlex
import shutil
import tempfile

from core.media_analyzer import detect_dolby_vision
from core.dolby_vision import (
    DolbyVisionError, apply_dolby_vision, dovi_tool_available, extract_rpu,
    mkvmerge_available,
)

log = logging.getLogger(__name__)


def _tag(tags, name):
    """Case-insensitive tag lookup that also accepts mkvmerge '-eng' suffixes."""
    name = name.upper()
    for key, value in (tags or {}).items():
        k = key.upper()
        if k == name or k.startswith(name + "-"):
            return value
    return ""


def _parse_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _run_ffprobe_streams(src, stream_type):
    """
    Generic helper to get stream info from ffprobe.
    stream_type: 'a' (audio) or 's' (subtitle).
    Returns list of dicts with keys: index, codec_name, profile, language,
    title, forced (bool), frames (int|None, from the MakeMKV/mkvmerge
    NUMBER_OF_FRAMES statistics tag).

    JSON output is used so titles containing commas and optional tags
    cannot shift fields the way CSV output could.
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        stream_type,
        "-show_entries",
        "stream=index,codec_name,profile:stream_disposition=forced:stream_tags",
        "-of",
        "json",
        src,
    ]
    log.debug(f"ffprobe CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"ffprobe failed for {src}: {result.stderr.strip()}")
        return []
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as e:
        log.warning(f"ffprobe returned unparseable JSON for {src}: {e}")
        return []
    return [_stream_from_probe(st) for st in data.get("streams", [])]


def _stream_from_probe(st):
    tags = st.get("tags") or {}
    disposition = st.get("disposition") or {}
    return {
        "index": str(st.get("index", "")),
        "codec_name": st.get("codec_name", "") or "",
        "profile": st.get("profile", "") or "",
        "language": _tag(tags, "language"),
        "title": _tag(tags, "title"),
        "forced": bool(_parse_int(disposition.get("forced")) or 0),
        "frames": _parse_int(_tag(tags, "NUMBER_OF_FRAMES")),
    }

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

# A forced-only subset (MakeMKV splits on-disc forced captions, e.g. Klingon
# dialogue, into their own track) carries a small fraction of the full
# track's caption events: 42 of 2456 on Star Trek: The Motion Picture.
# Full alternates (SDH, commentary) are comparable in size to the primary.
FORCED_SUBSET_MAX_RATIO = 0.10


def _is_english_or_untagged(s):
    lang = (s.get("language") or "").lower()
    return lang in ("eng", "en", "", "und")


def _select_first_english_sub(sub_streams):
    """
    Return index of first English (or untagged) subtitle stream, or None.
    Kept for callers that only need the primary track; see
    ``_select_english_subs`` for primary + forced selection.
    """
    primary, _ = _select_english_subs(sub_streams)
    return primary["index"] if primary else None


def _select_english_subs(sub_streams):
    """
    Return (primary, forced) subtitle stream dicts; either may be None.

    primary: first English/untagged track that is not a forced subset.
    forced:  English/untagged forced-caption track, chosen in order:
        1. a track whose container disposition is already forced;
        2. a track whose NUMBER_OF_FRAMES is at most
           FORCED_SUBSET_MAX_RATIO of the primary's. MakeMKV writes its
           forced subsets as Forced=No, Default=Yes, so the flag alone
           does not find them.
    If the only English track is a forced subset it is still returned as
    the primary, so behavior never regresses to "no subtitle".
    """
    english = [s for s in sub_streams if _is_english_or_untagged(s)]
    if not english:
        return None, None

    flagged = [s for s in english if s.get("forced")]
    unflagged = [s for s in english if not s.get("forced")]
    primary = unflagged[0] if unflagged else english[0]

    forced = next((s for s in flagged if s is not primary), None)
    if forced is None:
        primary_frames = primary.get("frames")
        if primary_frames:
            # Prefer the subset that is a true subset of the primary, i.e.
            # small; if the primary itself turned out to be a subset of a
            # later full track, swap them.
            for s in english:
                if s is primary or not s.get("frames"):
                    continue
                if s["frames"] <= primary_frames * FORCED_SUBSET_MAX_RATIO:
                    forced = s
                    break
                if primary_frames <= s["frames"] * FORCED_SUBSET_MAX_RATIO:
                    primary, forced = s, primary
                    break
    return primary, forced


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
    'source_profile': int|None}. Callers use ``enabled`` to gate RPU
    extraction and the post-encode inject/remux/verify step.

    Rules:
        - Only the UHD profile (name == '4k') ever preserves DV.
        - dolby_vision='off': always disabled.
        - dolby_vision='auto': enabled iff source has DV and both
          dovi_tool and mkvmerge are on PATH; otherwise HDR10 with a warning.
        - dolby_vision='p81'/'p76': force enabled; raise if source has
          no DV or either tool is missing.
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
        if not mkvmerge_available():
            log.warning(
                "Dolby Vision: source has DV Profile %s but mkvmerge is not "
                "on PATH; falling back to HDR10-only. Install mkvtoolnix to "
                "preserve DV, or pass --dolby-vision off to silence this.",
                src_profile,
            )
            return {"enabled": False, "target_profile": None, "source_profile": src_profile}
        log.info("Dolby Vision: source has DV Profile %s; will inject as P8.1 after encode.", src_profile)
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
    if not mkvmerge_available():
        raise DolbyVisionError(
            f"--dolby-vision {dolby_vision} requested but mkvmerge is not on PATH"
        )
    log.info("Dolby Vision: forced %s; source DV Profile %s.", dolby_vision, src_profile)
    return {"enabled": True, "target_profile": dolby_vision, "source_profile": src_profile}


# ffmpeg/libx265 report bad x265 options as warnings and keep encoding,
# so a typo or CLI-only option silently changes the output. Treat these as
# fatal before committing to a multi-hour encode. Generic "x265 [error]"
# lines are deliberately not matched: x265 emits advisory HDR10-opt
# messages at that level that do not affect the encode.
_PREFLIGHT_FATAL = re.compile(
    r"Unknown option|Invalid value|Error parsing option|Error setting option",
    re.IGNORECASE,
)


def _preflight_video_args(src, input_args, video_args, dry_run=False):
    """
    Encode one frame of ``src`` to the null muxer with the real video args.

    Returns (ok: bool, findings: list[str]). Any non-zero exit or any
    stderr line matching ``_PREFLIGHT_FATAL`` fails the preflight.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "warning",
        *input_args, "-i", src,
        "-map", "0:v:0", "-frames:v", "1", "-an", "-sn",
        *video_args, "-f", "null", "-",
    ]
    log.info(f"Preflight CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    if dry_run:
        log.info("--dry-run: skipping encoder preflight")
        return True, []
    proc = subprocess.run(cmd, capture_output=True, text=True)
    findings = [ln.strip() for ln in (proc.stderr or "").splitlines()
                if _PREFLIGHT_FATAL.search(ln)]
    if proc.returncode != 0 and not findings:
        findings = [f"ffmpeg exited rc={proc.returncode}: "
                    f"{(proc.stderr or '').strip()[-500:]}"]
    return (proc.returncode == 0 and not findings), findings


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

    primary_sub, forced_sub = _select_english_subs(sub_streams)
    if forced_sub is not None:
        log.info(
            "Subtitles: primary stream %s (%s events), forced stream %s "
            "(%s events, source forced flag=%s)",
            primary_sub["index"], primary_sub.get("frames"),
            forced_sub["index"], forced_sub.get("frames"), forced_sub.get("forced"),
        )
    elif primary_sub is not None:
        log.info("Subtitles: primary stream %s; no forced subset found",
                 primary_sub["index"])

    input_args = profile.get("input_args", [])

    ok, findings = _preflight_video_args(src, input_args, profile["video_args"],
                                         dry_run=dry_run)
    if not ok:
        for f in findings:
            log.error("Encoder preflight: %s", f)
        log.error("Encoder preflight failed for %s; not starting encode.", src)
        return subprocess.CompletedProcess(args=[], returncode=1)

    dv_plan = _plan_dolby_vision(src, profile, dolby_vision)
    dv_rpu_path = None
    dv_tmpdir = None
    encode_target = output_file
    if dv_plan["enabled"]:
        # Scratch lives beside the output, not in /tmp: it holds a full
        # HDR10 encode plus one HEVC elementary stream during injection.
        out_dir = os.path.dirname(output_file) or "."
        dv_tmpdir = tempfile.mkdtemp(prefix=".cinne-dv-", dir=out_dir)
        dv_rpu_path = os.path.join(dv_tmpdir, "rpu.bin")
        encode_target = os.path.join(dv_tmpdir, "encode_hdr10.mkv")
        try:
            extract_rpu(src, dv_rpu_path,
                        target_profile=dv_plan["target_profile"],
                        dry_run=dry_run)
        except DolbyVisionError:
            _cleanup_dv_tmp(dv_tmpdir)
            raise
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
    if primary_sub is not None:
        sub_args = ["-c:s", "copy"]
        out_pos = 0
        # Primary first: full English, not default, not forced (unchanged).
        # Forced second: default+forced so players show it without the
        # viewer enabling subtitles, matching disc behavior.
        for sub, disposition, title in (
            (primary_sub, "0", None),
            (forced_sub, "default+forced", "English (Forced)"),
        ):
            if sub is None:
                continue
            map_args += ["-map", f"0:{sub['index']}"]
            sub_lang = _normalize_language_tag(sub.get("language"), fallback="eng")
            sub_args += [f"-disposition:s:{out_pos}", disposition]
            sub_metadata_args += [f"-metadata:s:s:{out_pos}", f"language={sub_lang}"]
            if title:
                sub_metadata_args += [f"-metadata:s:s:{out_pos}", f"title={title}"]
            out_pos += 1

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y",
        *input_args,
        "-i",
        src,
        *map_args,
        # Strip global metadata and video-stream tags (MakeMKV/mkvmerge
        # statistics tags would be stale after a re-encode). Do NOT use a
        # bare "-map_metadata -1": it also disables chapter metadata, so
        # -map_chapters 0 copies chapter times but drops every chapter
        # title (verified on ffmpeg 8.0). The ":g" form leaves chapter
        # metadata on its default copy path. Stream tags are still manual
        # because of ":s:v", so audio titles/languages are re-attached
        # explicitly below. Do NOT add -map_metadata:c ...: ffmpeg parses
        # ':c' as "chapter N of output" and fails with "Invalid chapter
        # index 0" (PR #7 / #8).
        "-map_metadata:g",
        "-1",
        "-map_metadata:s:v",
        "-1",
        "-map_chapters",
        "0",
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
        encode_target,
    ]

    log.info(f"FFmpeg CMD: {' '.join(shlex.quote(c) for c in cmd)}")
    if dry_run:
        log.info("--dry-run: skipping ffmpeg execution for %s", encode_target)
        if dv_plan["enabled"]:
            apply_dolby_vision(encode_target, dv_rpu_path, output_file,
                               dv_tmpdir, dry_run=True)
        _cleanup_dv_tmp(dv_tmpdir)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        log.error(f"Encode failed (rc={result.returncode}) for {src}")
        if os.path.isfile(encode_target):
            os.remove(encode_target)
        _cleanup_dv_tmp(dv_tmpdir)
        return result
    if not os.path.isfile(encode_target):
        log.error(f"Encode returned success but output file missing: {encode_target}")
        _cleanup_dv_tmp(dv_tmpdir)
        return subprocess.CompletedProcess(args=cmd, returncode=1)
    if os.path.getsize(encode_target) < 1024:
        log.error(
            f"Suspiciously small output ({os.path.getsize(encode_target)} bytes): {encode_target}"
        )
        _cleanup_dv_tmp(dv_tmpdir)
        return subprocess.CompletedProcess(args=cmd, returncode=1)

    if dv_plan["enabled"]:
        try:
            apply_dolby_vision(encode_target, dv_rpu_path, output_file, dv_tmpdir)
        except DolbyVisionError as e:
            log.error("Dolby Vision injection failed for %s: %s", src, e)
            if os.path.isfile(output_file):
                os.remove(output_file)
            log.error(
                "HDR10 encode and RPU kept for inspection in %s "
                "(encode_hdr10.mkv, rpu.bin).", dv_tmpdir,
            )
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        _cleanup_dv_tmp(dv_tmpdir)

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