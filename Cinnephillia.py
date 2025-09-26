import os
import sys
import subprocess
import logging
import getpass
import pwd
import grp
import json
import argparse
import re

HANDBRAKE_CLI = "HandBrakeCLI"

# Path/names must match your HandBrake GUI exported custom presets.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CUSTOM_PRESETS = {
    "bluray": {
        # Assumes 'bluray_preset.json' is located in the same directory as the script
        "file": os.path.join(SCRIPT_DIR, "Home_Theater_HQ_-_x265_10bit_CRF18.json"),
        "name": "Home Theater HQ - x265 10bit CRF18"
    },
    "4k": {
        # Assumes 'uhd_preset.json' is located in the same directory as the script
        "file": os.path.join(SCRIPT_DIR, "Home_Theatre_4K_-_x265_10bit_CRF20.json"),
        "name": "Home Theatre 4K - x265 10bit CRF20"
    }
}

EXTRA_FOLDERS = [
    "Behind The Scenes", "Deleted Scenes", "Featurettes",
    "Interviews", "Other", "Shorts", "Trailers"
]

logging.basicConfig(
    filename="handbrake_batch.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def ensure_dir_permissions(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    user = getpass.getuser()
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(user).gr_gid
    os.chown(out_dir, uid, gid)
    os.chmod(out_dir, 0o775)

def get_movie_info(root_path):
    base = os.path.basename(root_path.rstrip(os.sep))
    if " (" in base and base.endswith(")"):
        title, year = base.rsplit(" (", 1)
        year = year.rstrip(")")
        return title, year
    return base, ""

def identify_main_feature(files):
    return max(files, key=lambda x: os.path.getsize(x)) if files else None

def detect_resolution(mkv_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", mkv_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        probe = json.loads(result.stdout)
        stream = probe["streams"][0]
        return stream["width"], stream["height"]
    except Exception as e:
        logging.error(f"ffprobe failed for {mkv_path}: {e}")
        return None, None

def select_preset(width, height):
    if width is None or height is None:
        logging.info("Could not detect resolution, using BluRay profile.")
        return CUSTOM_PRESETS["bluray"]
    if width >= 3840 or height >= 2160:
        logging.info(f"Main feature detected as 4K ({width}x{height}).")
        return CUSTOM_PRESETS["4k"]
    else:
        logging.info(f"Main feature detected as BluRay ({width}x{height}).")
        return CUSTOM_PRESETS["bluray"]

def process_main_feature(src, out_dir, title, year, preset):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{title} ({year}).mkv")
    cmd = [
        HANDBRAKE_CLI,
        "--preset-import-file", preset["file"],
        "--preset", preset["name"],
        "-i", src,
        "-o", output_file,
        "--all-subtitles",
        "--all-audio",
        "-f", "mkv"
    ]
    logging.info(f"HandBrakeCLI CMD (main feature): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    logging.info(f"{output_file} | {out_dir} | {preset['name']}")
    if result.returncode != 0:
        logging.error(f"Main feature failed: {result.stderr}")
    else:
        logging.info("Main feature processed successfully.")

def process_extra(src, out_dir, base, extra_preset_name):
    ensure_dir_permissions(out_dir)
    output_file = os.path.join(out_dir, f"{base}.mkv")
    cmd = [
        HANDBRAKE_CLI,
        "--preset", extra_preset_name,
        "-i", src,
        "-o", output_file,
        "-a", "1", "--subtitle=1", "-f", "mkv"
    ]
    logging.info(f"HandBrakeCLI CMD (extras): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    logging.info(f"{output_file} | {out_dir} | {extra_preset_name}")

    if result.returncode != 0:
        logging.error(f"Extra failed: {result.stderr}")
    else:
        logging.info("Extra processed successfully.")



def main(movie_root, mode):
    title, year = get_movie_info(movie_root)
    rip_path = os.path.join(movie_root, "rip")
    plex_root = os.path.join(movie_root, "Plex Movie Files")
#   preset = CUSTOM_PRESETS["bluray"]

    if not os.path.isdir(rip_path):
        msg = f"ERROR: rip folder not found: {rip_path}"
        logging.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    movies = [f for f in os.listdir(rip_path) if f.lower().endswith(".mkv")]
    full_paths = [os.path.join(rip_path, f) for f in movies]
    logging.info(f"Rip path: {rip_path}")
    logging.info(f"MKV files found: {movies}")

    if not full_paths:
        logging.warning(f"No MKV files in: {rip_path}")
        return

    main_feature = identify_main_feature(full_paths)
    extras = [f for f in full_paths if f != main_feature]

    if mode in ("feature", "both") and main_feature:
        width, height = detect_resolution(main_feature)
        preset = select_preset(width, height)
        process_main_feature(main_feature, plex_root, title, year, preset)

    EXTRAS_PRESET = "H.265 MKV 720p30"
    if mode in ("extras", "both"):
        for extra in extras:
            extra_base = os.path.splitext(os.path.basename(extra))[0]
            assigned = False
            for folder in sorted(EXTRA_FOLDERS, key=len, reverse=True):
                folder_token = folder.replace(" ", "[ _-]").lower()
                pattern = re.compile(rf"(.+)[ _-]{folder_token}$", re.IGNORECASE)
                match = pattern.match(extra_base)
                if match:
                    trimmed_name = match.group(1).strip(" _-")
                    out_dir = os.path.join(plex_root, folder)
                    process_extra(extra, out_dir, trimmed_name, EXTRAS_PRESET)
                    assigned = True
                    break
            if not assigned:
                out_dir = os.path.join(plex_root, "Other")
                process_extra(extra, out_dir, extra_base, EXTRAS_PRESET)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Handbrake batch script")
    parser.add_argument("path", help="Path to Movie Title (YYYY)")
    parser.add_argument("--mode", choices=["feature", "extras", "both"], default="both",
                        help="Process main feature, extras, or both.")
    args = parser.parse_args()

    main(args.path, args.mode)
