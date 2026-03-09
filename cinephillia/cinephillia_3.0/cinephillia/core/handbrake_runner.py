import os
import subprocess
import logging

log = logging.getLogger(__name__)

HANDBRAKE_CLI_BASE = [
    "flatpak", "run",
    "--command=HandBrakeCLI",
]

FLATPAK_APP = "fr.handbrake.ghb"

PROFILES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "profiles")
)


def _build_filesystem_flags(*paths):
    """Generate --filesystem flags for all unique directories flatpak needs."""
    dirs = set()
    for p in paths:
        if p:
            dirs.add(os.path.dirname(os.path.abspath(p)))
    return [f"--filesystem={d}" for d in sorted(dirs)]


def encode_with_preset(src, output_file, preset, audio_args=None, extra_flags=None):
    """
    Run HandBrakeCLI with the given preset dict and optional audio/flag overrides.
    Automatically grants flatpak filesystem access to input, output, and preset paths.
    """
    preset_file = os.path.normpath(preset["file"])
    fs_flags = _build_filesystem_flags(src, output_file, preset_file)

    cmd = list(HANDBRAKE_CLI_BASE) + fs_flags + [FLATPAK_APP]
    if audio_args:
        cmd += audio_args
    cmd += [
        "--all-subtitles",
        "-f", "mkv",
        "--preset-import-file", preset_file,
        "--preset", preset["name"],
        "-i", src,
        "-o", output_file,
    ]
    if extra_flags:
        cmd += extra_flags

    log.info(f"HandBrakeCLI CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stderr:
        log.debug(f"HandBrake stderr: {result.stderr[-500:]}")

    if result.returncode != 0:
        log.error(f"Encode failed (rc={result.returncode}) for {src}")
    elif not os.path.isfile(output_file):
        log.error(f"Encode returned success but output file missing: {output_file}")
    elif os.path.getsize(output_file) < 1024:
        log.error(f"Suspiciously small output ({os.path.getsize(output_file)} bytes): {output_file}")
    else:
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        log.info(f"Encode succeeded: {output_file} ({size_mb:.1f} MB)")

    return result


def encode_extra(src, output_file, preset_name):
    """Encode an extras file with a built-in preset (no custom JSON)."""
    fs_flags = _build_filesystem_flags(src, output_file)

    cmd = list(HANDBRAKE_CLI_BASE) + fs_flags + [FLATPAK_APP] + [
        "--preset", preset_name,
        "-i", src,
        "-o", output_file,
        "-a", "1", "--subtitle=1", "-f", "mkv",
    ]
    log.info(f"HandBrakeCLI CMD (extras): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.error(f"Extra encode failed: {result.stderr}")
    elif not os.path.isfile(output_file):
        log.error(f"Extra encode returned success but output file missing: {output_file}")
    else:
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        log.info(f"Extra encode succeeded: {output_file} ({size_mb:.1f} MB)")

    return result