import logging

log = logging.getLogger(__name__)

EXTRAS_PRESET_NAME = "extras_720p"  # used just as a label


def select_preset(width, height):
    """
    Choose an ffmpeg profile based on resolution.
    Returns a dict with keys:
      - name: label
      - input_args: list[str] for ffmpeg input-side options (optional)
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
        "input_args": [
            "-vaapi_device", "/dev/dri/renderD128",
        ],
        "video_args": [
            "-vf", "format=nv12,hwupload",
            "-c:v", "hevc_vaapi",
            "-b:v", "5M",
        ],
    }

def _bluray_profile():
    return {
        "name": "bluray",
        "input_args": [],
        "video_args": [
            "-c:v", "libx265",
            "-pix_fmt", "yuv420p",
            "-preset", "slow",
            "-crf", "20",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            "-x265-params", "repeat-headers=1",
        ],
    }

def _uhd_profile():
    return {
        "name": "4k",
        "input_args": [],
        "video_args": [
            "-c:v", "libx265",
            "-pix_fmt", "yuv420p10le",
            "-preset", "slow",
            "-crf", "23",
            "-color_primaries", "bt2020",
            "-color_trc", "smpte2084",
            "-colorspace", "bt2020nc",
            "-x265-params", "hdr10=1:hdr10-opt=1:repeat-headers=1",
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
    if key == "uhd":
        p = _uhd_profile()
    elif key == "sd_dvd":
        p = _sd_profile()
    else:
        p = _bluray_profile()
    log.info(f"Profile override: --encode {encode_profile} → {p['name']}")
    return p