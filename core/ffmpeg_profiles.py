import logging

log = logging.getLogger(__name__)

# These profiles are intentionally similar to your HandBrake presets,
# but expressed in ffmpeg terms instead of JSON HandBrake presets.
# You can tune qp, filters, etc. to taste.

EXTRAS_PRESET_NAME = "extras_720p"  # used just as a label


def select_preset(width, height):
    """
    Choose an ffmpeg profile based on resolution.
    Returns a dict with keys:
      - name: label
      - video_args: list[str] for ffmpeg video options
    """
    if width is None or height is None:
        log.info("Could not detect resolution, using BluRay/HD profile.")
        return _bluray_profile()

    if width >= 3840 or height >= 2160:
        log.info(f"Detected 4K ({width}x{height}).")
        return _uhd_profile()

    if width <= 720 or height <= 576:
        log.info(f"Detected SD/DVD ({width}x{height}).")
        return _sd_profile()

    log.info(f"Detected BluRay/HD ({width}x{height}).")
    return _bluray_profile()


def _sd_profile():
    return {
        "name": "sd",
        "video_args": [
            # SD / DVD → 8‑bit encode
            "-vf", "format=nv12,hwupload",
            "-c:v", "hevc_vaapi",
            "-b:v", "5M",
            # You can add: "-profile:v", "main",
        ],
    }


def _bluray_profile():
    return {
        "name": "bluray",
        "video_args": [
            # 1080p Blu‑ray: choose 8‑bit or 10‑bit depending on what you want.
            # If you want 8‑bit HEVC:
            "-vf", "format=nv12,hwupload",
            "-c:v", "hevc_vaapi",
            "-rc_mode", "CQP",
            "-qp", "22",
            "-profile:v", "main",
            # If you prefer 10‑bit here instead, change the two lines above to:
            # "-vf", "format=p010,hwupload",
            # "-profile:v", "main10",
        ],
    }


def _uhd_profile():
    return {
        "name": "4k",
        "video_args": [
            # 4K / UHD, 10‑bit Main10
            "-vf", "format=p010,hwupload",
            "-c:v", "hevc_vaapi",
            "-rc_mode", "CQP",
            "-qp", "24",
            "-profile:v", "main10",
        ],
    }


PROFILE_ALIASES = {
    "4k": "uhd",
    "bluray": "bluray",
    "dvd": "sd_dvd",
    "sd": "sd_dvd",
}


def get_preset_override(encode_profile):
    """Return profile dict for a CLI --encode override in future, if you add it."""
    key = PROFILE_ALIASES[encode_profile]
    # Reuse the helpers:
    if key == "uhd":
        p = _uhd_profile()
    elif key == "sd_dvd":
        p = _sd_profile()
    else:
        p = _bluray_profile()
    log.info(f"Profile override: --encode {encode_profile} → {p['name']}")
    return p