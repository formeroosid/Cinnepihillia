# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Run with: python3 -m unittest discover -s tests -p 'test_dolby_vision.py' -v"""
import json
import subprocess
import unittest
from unittest.mock import patch

from core import dolby_vision as dv


class DolbyVisionTests(unittest.TestCase):
    def identify(self, properties):
        return subprocess.CompletedProcess([], 0, json.dumps({
            "tracks": [{"type": "audio", "properties": {}},
                       {"type": "video", "properties": properties}],
            "errors": [],
        }), "")

    def test_json_packet_count_and_command(self):
        result = subprocess.CompletedProcess([], 0, '{"streams":[{"nb_read_packets":"723"}]}', "")
        with patch.object(dv, "_run_checked", return_value=result) as run:
            self.assertEqual(dv.video_frame_count("sample.mkv"), 723)
            self.assertIn("json", run.call_args.args[0])
            self.assertIn("-count_packets", run.call_args.args[0])

    def test_invalid_packet_counts(self):
        for value in ["N/A", "0", "-1", "723,", True, None, []]:
            with self.subTest(value=value):
                result = subprocess.CompletedProcess([], 0, json.dumps({
                    "streams": [{"nb_read_packets": value}]}), "")
                with patch.object(dv, "_run_checked", return_value=result):
                    with self.assertRaises(dv.DolbyVisionError):
                        dv.video_frame_count("sample.mkv")

    def test_json_frame_rate(self):
        for rate in ["24000/1001", "0/1", "24/0", "24000/1001,", "bad"]:
            result = subprocess.CompletedProcess([], 0, json.dumps({
                "streams": [{"r_frame_rate": rate}]}), "")
            with self.subTest(rate=rate), patch.object(dv, "_run_checked", return_value=result):
                if rate == "24000/1001":
                    self.assertEqual(dv.video_frame_rate("x"), rate)
                else:
                    with self.assertRaises(dv.DolbyVisionError):
                        dv.video_frame_rate("x")

    def test_malformed_probe_results(self):
        for text in ["not json", "{}", '{"streams":[]}', '{"streams":[{},{}]}']:
            with self.subTest(text=text), patch.object(dv, "_run_checked", return_value=
                    subprocess.CompletedProcess([], 0, text, "")):
                with self.assertRaises(dv.DolbyVisionError):
                    dv.video_frame_count("x")

    def test_hdr_mapping_and_track_selection(self):
        props = {
            "color_matrix_coefficients": 9, "color_range": 1,
            "color_transfer_characteristics": 16, "color_primaries": 9,
            "chromaticity_coordinates": "0.68,0.32,0.265,0.69,0.15,0.06",
            "white_color_coordinates": "0.3127,0.329",
            "min_luminance": 0.005, "max_luminance": 4000,
            "max_content_light": 1269, "max_frame_light": 52,
        }
        with patch.object(dv, "_run_checked", return_value=self.identify(props)):
            hdr = dv.read_hdr_properties("encoded.mkv")
        args = dv.hdr_remux_args(hdr)
        self.assertEqual(len(args), 20)
        self.assertIn("0:0.68,0.32,0.265,0.69,0.15,0.06", args)
        self.assertEqual(args[args.index("--max-content-light") + 1], "0:1269")
        self.assertEqual(args[args.index("--min-luminance") + 1], "0:0.005")

    def test_values_are_not_hardcoded(self):
        with patch.object(dv, "_run_checked", return_value=self.identify({
                "max_luminance": 1000, "max_content_light": 700, "max_frame_light": 100})):
            args = dv.hdr_remux_args(dv.read_hdr_properties("other.mkv"))
        self.assertIn("0:1000", args)
        self.assertIn("0:700", args)
        self.assertNotIn("0:1269", args)

    def test_absent_and_zero_values(self):
        with patch.object(dv, "_run_checked", return_value=self.identify({})):
            self.assertEqual(dv.read_hdr_properties("x"), {})
        self.assertEqual(dv.hdr_remux_args({}), [])
        with patch.object(dv, "_run_checked", return_value=self.identify({"max_content_light": 0})):
            self.assertEqual(dv.hdr_remux_args(dv.read_hdr_properties("x")),
                             ["--max-content-light", "0:0"])

    def test_invalid_hdr_values_fail_closed(self):
        for props in [{"min_luminance": -1}, {"max_luminance": "NaN"},
                      {"max_content_light": True}, {"max_frame_light": 1.5},
                      {"white_color_coordinates": "0.1"},
                      {"white_color_coordinates": "1.1,0.2"},
                      {"min_luminance": 10, "max_luminance": 1}]:
            with self.subTest(props=props), patch.object(dv, "_run_checked", return_value=self.identify(props)):
                with self.assertRaises(dv.DolbyVisionError):
                    dv.read_hdr_properties("x")

    def test_bad_identification(self):
        for text in ["bad", "[]", "{}", '{"tracks":[]}', '{"errors":["failure"]}']:
            with self.subTest(text=text), patch.object(dv, "_run_checked", return_value=
                    subprocess.CompletedProcess([], 0, text, "")):
                with self.assertRaises(dv.DolbyVisionError):
                    dv.read_hdr_properties("x")

    def test_hdr_verification_tolerance_and_loss(self):
        expected = {"min_luminance": (0.005,), "max_content_light": (1269,)}
        with patch.object(dv, "read_hdr_properties", return_value={
                "min_luminance": (0.0049999999,), "max_content_light": (1269,)}):
            dv.verify_hdr_properties("out", expected)
        for actual in [{}, {"min_luminance": (0.005,), "max_content_light": (0,)}]:
            with patch.object(dv, "read_hdr_properties", return_value=actual):
                with self.assertRaises(dv.DolbyVisionError):
                    dv.verify_hdr_properties("out", expected)

    def test_remux_option_placement_and_verification(self):
        hdr = {"max_content_light": (1269,), "max_frame_light": (52,)}
        with patch.object(dv, "rpu_frame_count", return_value=723), \
             patch.object(dv, "video_frame_count", return_value=723), \
             patch.object(dv, "video_frame_rate", return_value="24000/1001"), \
             patch.object(dv, "read_hdr_properties", return_value=hdr), \
             patch.object(dv, "_run_checked") as run, \
             patch.object(dv.os, "remove"), \
             patch.object(dv, "detect_dolby_vision", return_value={"present": True, "profile": 8}), \
             patch.object(dv, "verify_hdr_properties") as verify:
            dv.apply_dolby_vision("encoded.mkv", "rpu.bin", "out.mkv", "/scratch")
            cmd = run.call_args_list[-1].args[0]
            self.assertLess(cmd.index("--max-content-light"), cmd.index("/scratch/video_dv.hevc"))
            self.assertGreater(cmd.index("--no-video"), cmd.index("/scratch/video_dv.hevc"))
            verify.assert_called_once_with("out.mkv", hdr)

    def test_frame_mismatch_stops_before_injection(self):
        with patch.object(dv, "rpu_frame_count", return_value=723), \
             patch.object(dv, "video_frame_count", return_value=722), \
             patch.object(dv, "_run_checked") as run:
            with self.assertRaises(dv.DolbyVisionError):
                dv.apply_dolby_vision("in", "rpu", "out", "/scratch")
            run.assert_not_called()

    def test_dry_run_has_no_subprocesses(self):
        with patch.object(dv.subprocess, "run") as run:
            self.assertEqual(dv.apply_dolby_vision("in", "rpu", "out", "/scratch", dry_run=True), "out")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
