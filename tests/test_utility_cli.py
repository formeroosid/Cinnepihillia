"""Regression tests for source selection and side-effect-free CLI help."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get("UTILITY_TEST_ROOT", Path(__file__).resolve().parents[1]))
SCRIPTS = ("copy_plex_movies.sh", "copy_plex_tv.sh", "cp2movie.sh", "cp2tv.sh", "refresh-repomix.sh")

class UtilityCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.log = self.cwd / "operations.log"
        tools = self.cwd / "bin"
        tools.mkdir()
        for tool in ("hostname", "rsync", "curl", "repomix", "realpath", "findmnt", "mountpoint", "mkdir", "find", "sort"):
            mock = tools / tool
            mock.write_text('#!/bin/sh\nprintf "%s\\n" "$0" >> "$OPERATION_LOG"\nexit 99\n')
            mock.chmod(0o755)
        self.env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""), OPERATION_LOG=str(self.log), REPO_DIR=str(self.cwd))

    def invoke(self, script, args):
        self.log.unlink(missing_ok=True)
        result = subprocess.run([shutil.which("bash"), str(ROOT / "utils" / script), *args], cwd=self.cwd, env=self.env, capture_output=True, text=True, timeout=5)
        operations = self.log.read_text() if self.log.exists() else ""
        return result, operations

    def test_syntax(self):
        for script in SCRIPTS:
            with self.subTest(script=script):
                subprocess.run([shutil.which("bash"), "-n", str(ROOT / "utils" / script)], check=True, capture_output=True)

    def test_help_and_invalid_arguments_never_start_operations(self):
        for script in SCRIPTS:
            cases = [([], 2), (["-h"], 0), (["--help"], 0), (["--unknown"], 2)]
            if script.startswith("copy_"):
                cases += [(["-n"], 2), (["one-path"], 2), (["a", "b", "c"], 2), (["", "dest"], 2), (["--mount"], 2), (["--mount", "--name", "x"], 2), (["source", "--help"], 0)]
            elif script.startswith("cp2"):
                cases += [(["--source"], 2), (["--source", ""], 2), (["--source", "--no-refresh"], 2), (["."], 2), (["--source", ".", "--help"], 0), (["--name", "a/b"], 2), (["-n", "--help"], 0)]
            else:
                cases += [(["--source"], 2), (["--source", ""], 2), (["--output", "bundle.md"], 2), (["--source", "--output", "x"], 2), (["."], 2), (["--source", ".", "--help"], 0)]
            for args, status in cases:
                with self.subTest(script=script, args=args):
                    result, operations = self.invoke(script, args)
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertIn("Usage:", result.stdout + result.stderr)
                    self.assertEqual(operations, "")

    def test_explicit_sources_reach_operational_validation(self):
        for script in SCRIPTS:
            args = ["-n", "/explicit/source", "/explicit/dest"] if script.startswith("copy_") else ["--source", str(self.cwd)]
            with self.subTest(script=script):
                result, operations = self.invoke(script, args)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(operations, result.stderr)

    def test_cp2_option_without_source_defaults_to_current_directory(self):
        for script in ("cp2movie.sh", "cp2tv.sh"):
            for args in (["-n"], ["--no-refresh"], ["-n", "--name", "Title"]):
                with self.subTest(script=script, args=args):
                    result, operations = self.invoke(script, args)
                    self.assertNotEqual(result.returncode, 2, result.stderr)
                    self.assertNotIn("Usage:", result.stderr)
                    self.assertTrue(operations, result.stderr)


class Cp2SourceGuardTests(unittest.TestCase):
    """Run the real source guards with a Lumpy hostname and logging rsync/curl mocks."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.log = base / "operations.log"
        tools = base / "bin"
        tools.mkdir()
        (tools / "hostname").write_text("#!/bin/sh\necho lumpy\n")
        for tool in ("rsync", "curl"):
            (tools / tool).write_text('#!/bin/sh\nprintf "%s\\n" "$0" >> "$OPERATION_LOG"\nexit 99\n')
        for mock in tools.iterdir():
            mock.chmod(0o755)
        self.home = base / "home"
        self.home.mkdir()
        self.media = base / "media" / "Show"
        self.media.mkdir(parents=True)
        (self.media / "episode.mkv").write_bytes(b"x")
        self.env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""), OPERATION_LOG=str(self.log), HOME=str(self.home))

    def invoke(self, script, args, cwd, script_path=None):
        self.log.unlink(missing_ok=True)
        path = script_path or ROOT / "utils" / script
        result = subprocess.run([shutil.which("bash"), str(path), *args], cwd=cwd, env=self.env, capture_output=True, text=True, timeout=5)
        return result, self.log.read_text() if self.log.exists() else ""

    def test_implicit_root_home_and_mount_roots_are_refused(self):
        for script in ("cp2movie.sh", "cp2tv.sh"):
            for cwd, needle in (("/", "Refusing /"), (self.home, "home directory"), ("/proc", "mount root")):
                with self.subTest(script=script, cwd=cwd):
                    result, operations = self.invoke(script, ["-n"], cwd)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(needle, result.stderr)
                    self.assertEqual(operations, "")

    def test_source_containing_script_is_refused_even_when_explicit(self):
        copy = self.media.parent / "cp2tv.sh"
        shutil.copy(ROOT / "utils" / "cp2tv.sh", copy)
        for args in (["-n"], ["-n", "--source", str(self.media.parent)]):
            with self.subTest(args=args):
                result, operations = self.invoke("cp2tv.sh", args, self.media.parent, script_path=copy)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("contains this script", result.stderr)
                self.assertEqual(operations, "")

    def test_implicit_source_passes_guards_and_resolves_current_directory(self):
        for script in ("cp2movie.sh", "cp2tv.sh"):
            with self.subTest(script=script):
                result, operations = self.invoke(script, ["-n"], self.media)
                self.assertNotIn("Refusing", result.stderr)
                self.assertNotIn("contains this script", result.stderr)
                self.assertEqual(operations, "")


if __name__ == "__main__":
    unittest.main()
