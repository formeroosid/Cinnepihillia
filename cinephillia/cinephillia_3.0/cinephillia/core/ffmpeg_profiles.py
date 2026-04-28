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
            # Match the working CLI: system memory -> nv12 -> hwupload -> hevc_vaapi
            "-vf", "format=nv12,hwupload",
            "-c:v", "hevc_vaapi",
            "-b:v", "5M",
            # Optional: let VAAPI choose profile/level from the input,
            # so we don't force something unsupported
            # "-profile:v", "main",
        ],
    }

def _bluray_profile():
    return {
        "name": "bluray",
        "video_args": [
            "-vf", "scale_vaapi=format=p010",
            "-c:v", "hevc_vaapi",
            "-rc_mode", "CQP",
            "-qp", "22",
            "-profile:v", "main10",
        ],
    }

def _uhd_profile():
    return {
        "name": "4k",
        "video_args": [
            "-vf", "scale_vaapi=format=p010",
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
