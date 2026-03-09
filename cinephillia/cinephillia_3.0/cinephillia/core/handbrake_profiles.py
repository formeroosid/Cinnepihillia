import os
import logging

log = logging.getLogger(__name__)

PROFILES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "profiles")
)

CUSTOM_PRESETS = {
    "sd_dvd": {
        "file": os.path.join(PROFILES_DIR, "Home_Theatre_SD_DVD_x265_10bit_CRF20.json"),
        "name": "SD-DVD",  # Verify this matches PresetName inside the JSON
    },
    "bluray": {
        "file": os.path.join(PROFILES_DIR, "Home_Theater_HQ_-_x265_10bit_CRF18.json"),
        "name": "my-home-theater-dtshd",
    },
    "4k": {
        "file": os.path.join(PROFILES_DIR, "Home_Theatre_4K_-_x265_10bit_CRF20.json"),
        "name": "UHD",
    },
}

EXTRAS_PRESET_NAME = "H.265 MKV 720p30"


def select_preset(width, height):
    """Choose a HandBrake preset based on video resolution."""
    if width is None or height is None:
        log.info("Could not detect resolution, using BluRay profile.")
        return CUSTOM_PRESETS["bluray"]
    if width >= 3840 or height >= 2160:
        log.info(f"Detected 4K ({width}x{height}).")
        return CUSTOM_PRESETS["4k"]
    if width <= 720 or height <= 576:
        log.info(f"Detected SD/DVD ({width}x{height}).")
        return CUSTOM_PRESETS["sd_dvd"]
    log.info(f"Detected BluRay/HD ({width}x{height}).")
    return CUSTOM_PRESETS["bluray"]
