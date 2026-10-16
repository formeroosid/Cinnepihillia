# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Hardware-independent regression tests for encoder backend selection."""
import copy
import unittest

from core.ffmpeg_profiles import apply_encoder_backend, select_preset


class EncoderBackendTests(unittest.TestCase):
    def option(self, profile, flag):
        args = profile["video_args"]
        return args[args.index(flag) + 1]

    def test_native_default(self):
        for width, height, name, codec in (
            (3840, 2160, "4k", "libx265"),
            (1920, 1080, "bluray", "libx265"),
            (720, 480, "sd", "hevc_vaapi"),
            (None, None, "bluray", "libx265"),
        ):
            with self.subTest(width=width, height=height):
                native = select_preset(width, height)
                self.assertEqual(native, select_preset(width, height, encoder="native"))
                self.assertEqual(native["name"], name)
                self.assertEqual(self.option(native, "-c:v"), codec)
                nvenc = select_preset(width, height, encoder="nvenc")
                self.assertEqual(nvenc["name"], name)
                self.assertEqual(self.option(nvenc, "-c:v"), "hevc_nvenc")

    def test_native_returns_original(self):
        profile = {"name": "sd", "input_args": [], "video_args": []}
        self.assertIs(apply_encoder_backend(profile), profile)

    def test_no_mutation(self):
        profile = {"name": "sd",
                   "input_args": ["-vaapi_device", "/dev/dri/renderD128"],
                   "video_args": ["-vf", "format=nv12,hwupload", "-c:v", "hevc_vaapi"]}
        before = copy.deepcopy(profile)
        result = apply_encoder_backend(profile, "nvenc")
        self.assertEqual(profile, before)
        self.assertIsNot(result, profile)
        self.assertIsNot(result["video_args"], profile["video_args"])
        self.assertIsNot(result["input_args"], profile["input_args"])

    def test_common_nvenc_options(self):
        for name in ("4k", "bluray", "sd"):
            with self.subTest(name=name):
                result = apply_encoder_backend({"name": name}, "nvenc")
                self.assertEqual(result["name"], name)
                self.assertEqual(result["input_args"], [])
                for flag, value in {"-c:v": "hevc_nvenc", "-gpu": "0",
                                    "-preset": "p6", "-tune": "hq", "-rc": "vbr",
                                    "-b:v": "0", "-fps_mode": "passthrough"}.items():
                    self.assertEqual(self.option(result, flag), value)
                for forbidden in ("-x265-params", "-crf", "-vaapi_device", "libx265", "hevc_vaapi"):
                    self.assertNotIn(forbidden, result["video_args"])
                self.assertNotIn("hwupload", self.option(result, "-vf"))

    def test_uhd(self):
        result = apply_encoder_backend({"name": "4k"}, "nvenc")
        for flag, value in {"-vf": "format=p010le", "-profile:v": "main10",
                            "-cq": "23", "-color_range": "tv",
                            "-color_primaries": "bt2020", "-color_trc": "smpte2084",
                            "-colorspace": "bt2020nc"}.items():
            self.assertEqual(self.option(result, flag), value)

    def test_hd_and_sd(self):
        for name in ("bluray", "sd"):
            with self.subTest(name=name):
                result = apply_encoder_backend({"name": name}, "nvenc")
                for flag, value in {"-vf": "format=nv12", "-profile:v": "main", "-cq": "20"}.items():
                    self.assertEqual(self.option(result, flag), value)
                for flag in ("-color_primaries", "-color_trc", "-colorspace"):
                    if name == "bluray":
                        self.assertEqual(self.option(result, flag), "bt709")
                    else:
                        self.assertNotIn(flag, result["video_args"])

    def test_invalid_backend_and_profile(self):
        with self.assertRaises(ValueError):
            apply_encoder_backend({"name": "4k"}, "invalid")
        with self.assertRaises(ValueError):
            apply_encoder_backend({"name": "unknown"}, "nvenc")


if __name__ == "__main__":
    unittest.main()
