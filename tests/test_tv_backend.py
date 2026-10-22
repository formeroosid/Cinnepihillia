# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

"""Hardware-independent TV backend, DV routing and failure regressions."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import Cinnephillia as entry
from tv import cli
from tv import tv_pipeline as tv


class TVBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rip = self.root / "rip"
        self.src = self.rip / "S03D01" / "episode_t00.mkv"
        self.src.parent.mkdir(parents=True)
        self.src.write_bytes(b"source")
        self.staging = self.root / "staging"
        self.output = self.root / "plex"
        self.target = self.staging / "S03D01" / self.src.name
        ep = {"path": self.src, "season": 3, "disc": 1, "title_num": 0}
        self.mock(tv, "parse_tv_input", return_value=[ep])
        self.resolution = self.mock(tv, "detect_resolution", return_value=(3840, 2160))
        self.select = self.mock(tv, "select_preset", return_value={"name": "4k"})
        self.mock(tv, "ensure_dir_permissions", side_effect=lambda p: Path(p).mkdir(parents=True, exist_ok=True))
        self.mock(tv, "sequential_inventory_report", return_value={})
        self.mock(tv, "print_sequential_inventory")
        self.render = self.mock(tv, "_render_sequential_files", return_value=[])
        self.encode = self.mock(tv, "encode_with_profile", side_effect=self.success)

    def mock(self, module, name, **kwargs):
        p = patch.object(module, name, **kwargs)
        self.addCleanup(p.stop)
        return p.start()

    def success(self, src, dest, profile, **kwargs):
        Path(dest).write_bytes(b"encoded")
        return subprocess.CompletedProcess([], 0)

    def run_tv(self, **kwargs):
        return tv.process_tv_series(self.rip, self.staging, self.output, "Series", **kwargs)

    def test_native_and_auto_defaults(self):
        self.run_tv()
        self.select.assert_called_once_with(3840, 2160, encoder="native")
        self.assertEqual(self.encode.call_args.kwargs,
                         {"preserve_all_audio": False, "dolby_vision": "auto"})
        self.render.assert_called_once()

    def test_nvenc_and_explicit_dv_modes(self):
        for mode in ("auto", "off", "p81", "p76"):
            with self.subTest(mode=mode):
                if self.target.exists():
                    self.target.unlink()
                self.run_tv(encoder="nvenc", dolby_vision=mode, preserve_all_audio=True)
                self.assertEqual(self.select.call_args.kwargs, {"encoder": "nvenc"})
                self.assertEqual(self.encode.call_args.kwargs,
                                 {"preserve_all_audio": True, "dolby_vision": mode})

    def test_nonzero_result_stops_before_render(self):
        self.encode.side_effect = None
        self.encode.return_value = subprocess.CompletedProcess([], 1)
        with self.assertRaises(RuntimeError):
            self.run_tv(encoder="nvenc")
        self.render.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_or_empty_output_stops(self):
        self.encode.side_effect = None
        self.encode.return_value = subprocess.CompletedProcess([], 0)
        for empty in (False, True):
            with self.subTest(empty=empty):
                if empty:
                    self.target.parent.mkdir(parents=True, exist_ok=True)
                    self.target.touch()
                with self.assertRaises(RuntimeError):
                    self.run_tv()
        self.render.assert_not_called()

    def test_encoder_exception_propagates(self):
        self.encode.side_effect = RuntimeError("DV failed")
        with self.assertRaisesRegex(RuntimeError, "DV failed"):
            self.run_tv(dolby_vision="p81")
        self.render.assert_not_called()

    def test_existing_output_is_skipped_with_warning(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"existing")
        with self.assertLogs(tv.log, level="WARNING") as logs:
            self.run_tv(encoder="nvenc", dolby_vision="p81")
        self.encode.assert_not_called()
        self.assertIn("NOT applied or verified", " ".join(logs.output))
        self.assertEqual(self.target.read_bytes(), b"existing")

    def test_dry_run_is_inventory_only(self):
        self.run_tv(encoder="nvenc", dolby_vision="p81", dry_run=True)
        self.encode.assert_not_called()
        self.select.assert_not_called()
        self.render.assert_not_called()
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.output.exists())

    def test_invalid_modes_fail_before_discovery(self):
        for kwargs in ({"encoder": "bad"}, {"dolby_vision": "bad"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_tv(**kwargs)
        tv.parse_tv_input.assert_not_called()

    def test_main_cli_forwards_tv_options(self):
        args = ["Cinnephillia.py", str(self.root), "--type", "tv", "--encoder", "nvenc",
                "--dolby-vision", "p81", "--preserve-all-audio", "--dry-run"]
        with patch.object(sys, "argv", args), patch.object(entry, "setup_logging"), \
             patch.object(entry, "process_tv_series") as process:
            entry.main()
        for key, value in {"encoder": "nvenc", "dolby_vision": "p81",
                           "preserve_all_audio": True, "dry_run": True}.items():
            self.assertEqual(process.call_args.kwargs[key], value)

    def test_main_cli_keeps_movie_routing(self):
        with patch.object(sys, "argv", ["Cinnephillia.py", str(self.root)]), \
             patch.object(entry, "setup_logging"), patch.object(entry, "process_movie") as process:
            entry.main()
        self.assertEqual(process.call_args.kwargs["encoder"], "native")
        self.assertEqual(process.call_args.kwargs["dolby_vision"], "auto")

    def test_tv_cli_options_and_defaults(self):
        base = ["tv.cli", "process", "--input", str(self.rip), "--staging", str(self.staging),
                "--output", str(self.output), "--series", "Series"]
        for extra, encoder, dv in (([], "native", "auto"),
                                   (["--encoder", "nvenc", "--dolby-vision", "p81"], "nvenc", "p81")):
            with self.subTest(encoder=encoder), patch.object(sys, "argv", base + extra), \
                 patch.object(cli, "setup_logging"), patch.object(cli, "process_tv_series") as process:
                cli.main()
                self.assertEqual(process.call_args.kwargs["encoder"], encoder)
                self.assertEqual(process.call_args.kwargs["dolby_vision"], dv)


if __name__ == "__main__":
    unittest.main()
