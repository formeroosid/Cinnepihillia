# SPDX-License-Identifier: MIT
# Copyright (c) 2026 formeroosid

import logging

log = logging.getLogger(__name__)
EXTRAS_PRESET_NAME = "extras_720p"  # used just as a label


NVENC_DEFAULT_CQ = {"4k": 19, "bluray": 20, "sd": 20}
NVENC_CQ_RANGE = (1, 51)


def validate_nvenc_cq(value):
    """Return an NVENC CQ override as int, or None when not supplied."""
    if value is None:
        return None
    cq = int(value)
    low, high = NVENC_CQ_RANGE
    if not low <= cq <= high:
        raise ValueError(f"NVENC CQ must be between {low} and {high}: {value!r}")
    return cq


def apply_encoder_backend(profile, encoder="native", nvenc_cq=None):
    """Select native profiles or NVIDIA HEVC without changing profile names.

    nvenc_cq overrides the per-profile NVENC constant-quality value. It is
    rejected for the native backend so a quality request is never ignored.
    """
    if encoder not in {"native", "nvenc"}:
        raise ValueError(f"Unsupported encoder backend: {encoder!r}")
    nvenc_cq = validate_nvenc_cq(nvenc_cq)
    if encoder == "native":
        if nvenc_cq is not None:
            raise ValueError("nvenc_cq requires encoder='nvenc'")
        return profile
    name = profile["name"]
    if name not in {"4k", "bluray", "sd"}:
        raise ValueError(f"Unsupported NVENC profile: {name!r}")
    is_uhd = name == "4k"
    cq = nvenc_cq if nvenc_cq is not None else NVENC_DEFAULT_CQ[name]
    video_args = [
        "-vf", "format=p010le" if is_uhd else "format=nv12",
        "-fps_mode", "passthrough",
        "-c:v", "hevc_nvenc",
        "-gpu", "0",
        "-profile:v", "main10" if is_uhd else "main",
        "-preset", "p6",
        "-tune", "hq",
        "-rc", "vbr",
        "-cq", str(cq),
        "-b:v", "0",
        # Quality tools: full-resolution two-pass rate control, lookahead,
        # spatial/temporal adaptive quantization (flat dark gradients and
        # static scenes), and B-frames used as references.
        "-multipass", "fullres",
        "-rc-lookahead", "32",
        "-spatial-aq", "1",
        "-temporal-aq", "1",
        "-aq-strength", "8",
        "-bf", "4",
        "-b_ref_mode", "middle",
    ]
    if is_uhd:
        video_args += [
            # Main tier caps Level 5.x near 25-40 Mb/s; lower CQ peaks exceed it.
            "-tier", "high",
            "-color_range", "tv",
            "-color_primaries", "bt2020",
            "-color_trc", "smpte2084",
            "-colorspace", "bt2020nc",
        ]
    elif name == "bluray":
        video_args += [
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
        ]
    # Do not force BT.709 onto SD sources.
    result = dict(profile)
    result["input_args"] = []
    result["video_args"] = video_args
    log.info("Encoder backend: nvenc; profile=%s; GPU=0; preset=p6; CQ=%s%s; "
             "multipass=fullres; lookahead=32; spatial/temporal AQ=on; bf=4",
             name, cq, " (override)" if nvenc_cq is not None else "")
    return result


def select_preset(width, height, encoder="native", nvenc_cq=None):
    """Choose a resolution profile and apply the encoder backend."""
    if width is None or height is None:
        log.info("Could not detect resolution, using BluRay/HD profile.")
        profile = _bluray_profile()
    elif width >= 3840 or height >= 2160:
        log.info(f"Detected 4K ({width}x{height}).")
        profile = _uhd_profile()
    elif width <= 720 or height <= 576:
        log.info(f"Detected SD/DVD ({width}x{height}).")
        profile = _sd_profile()
    else:
        log.info(f"Detected BluRay/HD ({width}x{height}).")
        profile = _bluray_profile()
    return apply_encoder_backend(profile, encoder, nvenc_cq=nvenc_cq)


def _sd_profile():
    return {
        "name": "sd",
        "input_args": ["-vaapi_device", "/dev/dri/renderD128"],
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
            "-x265-params",
            "repeat-headers=1:colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited",
        ],
    }


def _uhd_profile():
    # Dolby Vision is injected after encoding, not passed through x265 options.
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
