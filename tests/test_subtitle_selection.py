# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Regression tests for English primary + forced-subset subtitle selection."""
import json
import subprocess
import unittest
from unittest import mock

from core import ffmpeg_runner
from core.ffmpeg_runner import _select_english_subs, _select_first_english_sub


def sub(index, frames=None, lang="eng", forced=False, title=""):
    return {"index": str(index), "codec_name": "hdmv_pgs_subtitle", "profile": "",
            "language": lang, "title": title, "forced": forced, "frames": frames}


# Star Trek: The Motion Picture - Director's Edition (MakeMKV 2.0.0 rip):
# the forced subset follows each full English track, flagged Default=Yes,
# Forced=No.
STTMP = [sub(7, 2456), sub(8, 42), sub(9, 2762), sub(10, 42),
         sub(11, 5108), sub(12, 3842), sub(13, 2457)]


class SubtitleSelectionTests(unittest.TestCase):
    def pick(self, streams):
        primary, forced = _select_english_subs(streams)
        return (primary and primary["index"], forced and forced["index"])

    def test_makemkv_unflagged_subset(self):
        self.assertEqual(self.pick(STTMP), ("7", "8"))

    def test_flagged_forced_preferred(self):
        streams = [sub(3, 2000), sub(4, 1900), sub(5, 30, forced=True)]
        self.assertEqual(self.pick(streams), ("3", "5"))

    def test_flagged_forced_listed_first(self):
        streams = [sub(3, 30, forced=True), sub(4, 2000)]
        self.assertEqual(self.pick(streams), ("4", "3"))

    def test_unflagged_subset_listed_first(self):
        self.assertEqual(self.pick([sub(3, 40), sub(4, 2000)]), ("4", "3"))

    def test_alternate_full_track_not_forced(self):
        self.assertEqual(self.pick([sub(3, 2000), sub(4, 1800)]), ("3", None))

    def test_missing_frame_tags(self):
        self.assertEqual(self.pick([sub(3), sub(4)]), ("3", None))

    def test_other_language_ignored(self):
        streams = [sub(3, 30, lang="fre", forced=True), sub(4, 2000)]
        self.assertEqual(self.pick(streams), ("4", None))

    def test_only_subset_is_primary(self):
        self.assertEqual(self.pick([sub(3, 42)]), ("3", None))

    def test_none(self):
        self.assertEqual(self.pick([]), (None, None))
        self.assertIsNone(_select_first_english_sub([sub(3, lang="ger")]))

    def test_probe_parses_disposition_and_frames(self):
        payload = {"streams": [
            {"index": 7, "codec_name": "hdmv_pgs_subtitle",
             "disposition": {"forced": 0},
             "tags": {"language": "eng", "NUMBER_OF_FRAMES-eng": "2456"}},
            {"index": 8, "codec_name": "hdmv_pgs_subtitle",
             "disposition": {"forced": 1},
             "tags": {"language": "eng", "NUMBER_OF_FRAMES": "42", "title": "a, b"}},
        ]}
        done = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with mock.patch.object(ffmpeg_runner.subprocess, "run", return_value=done):
            streams = ffmpeg_runner._run_ffprobe_streams("x.mkv", "s")
        self.assertEqual([(s["index"], s["frames"], s["forced"]) for s in streams],
                         [("7", 2456, False), ("8", 42, True)])
        self.assertEqual(streams[1]["title"], "a, b")


class SubtitleCommandTests(unittest.TestCase):
    def command(self, subs):
        audio = [{"index": "1", "codec_name": "truehd", "profile": "", "language": "eng",
                  "title": "", "forced": False, "frames": None}]
        profile = {"name": "bluray", "input_args": [], "video_args": ["-c:v", "libx265"]}
        with mock.patch.object(ffmpeg_runner, "_run_ffprobe_streams",
                               side_effect=lambda src, t: audio if t == "a" else subs), \
             mock.patch.object(ffmpeg_runner, "_preflight_video_args",
                               return_value=(True, [])), \
             mock.patch.object(ffmpeg_runner.os, "makedirs"):
            return ffmpeg_runner.encode_with_profile(
                "in.mkv", "/out/x.mkv", profile, dolby_vision="off", dry_run=True).args

    def test_forced_mapped_and_flagged(self):
        cmd = self.command(STTMP)
        joined = " ".join(cmd)
        self.assertIn("-map 0:7 -map 0:8", joined)
        self.assertIn("-disposition:s:0 0", joined)
        self.assertIn("-disposition:s:1 default+forced", joined)
        self.assertIn("-metadata:s:s:1 title=English (Forced)", joined)
        self.assertNotIn("0:9", cmd)

    def test_primary_only_unchanged(self):
        joined = " ".join(self.command([sub(3, 2000)]))
        self.assertIn("-map 0:3", joined)
        self.assertIn("-disposition:s:0 0", joined)
        self.assertNotIn("disposition:s:1", joined)


if __name__ == "__main__":
    unittest.main()
