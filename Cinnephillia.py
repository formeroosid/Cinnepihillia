import os
import sys
import subprocess
import logging
import getpass
import pwd
import grp

# from datetime import datetime

# --- BEGIN CONFIG ---

HANDBRAKE_CLI = "HandBrakeCLI"  # or full path if not in PATH

PRESETS = {
    "main_feature": "H.265 MKV 1080p30",  # Replace with the actual HandBrake preset name or JSON file path
    "extras": "H.265 MKV 720p30"              # Replace with the actual HandBrake preset name or JSON file path
}
EXTRA_FOLDERS = [
    "Behind The Scenes",
    "Deleted Scenes",
    "Featurettes",
    "Interviews",
    "Other",
    "Scenes",
    "Shorts",
    "Trailers"
]

# --- END CONFIG ---


# Set up logger
logging.basicConfig(
    filename="handbrake_batch.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def get_movie_info(root_path):
    """Extract movie title and year from folder name."""
    base = os.path.basename(root_path.rstrip(os.sep))
    if " (" in base and base.endswith(")"):
        title, year = base.rsplit(" (", 1)
        year = year.rstrip(")")
        return title, year
    return base, ""


def identify_main_feature(files):
    """Identify the main feature file by largest size."""
    if not files:
        return None
    return max(files, key=lambda x: os.path.getsize(x))


def process_main_feature(src, out_dir, title, year):
    output_file = os.path.join(out_dir, f"{title} ({year}).mkv")
    preset = PRESETS['main_feature']
    cmd = [
        HANDBRAKE_CLI, "-i", src, "-o", output_file,
        "--preset", preset,
        "--all-audio", "--all-subtitles",
        "-E", "copy:ac3,copy:dts,copy:truehd,copy:eac3,copy:aac,copy:mp3,copy:flac,copy:opus,copy:vorbis,copy:pcm",
        "-f", "mkv"
    ]

    logging.info(f"HandBrakeCLI CMD (main feature): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    logging.info(f"{output_file} | {out_dir} | {preset} | Audio Passthrough")
    if result.returncode != 0:
        logging.error(f"Main feature failed: {result.stderr}")
    else:
        logging.info("Main feature processed successfully.")


def process_extra(src, out_dir, base, suffix, preset):
    output_file = os.path.join(out_dir, f"{base}.mkv")  # Suffix removed
    cmd = [
        HANDBRAKE_CLI, "-i", src, "-o", output_file,
        "--preset", preset,
        "-a", "1",         # Only first audio track
        "--all-subtitles",
        "-f", "mkv"
    ]
    logging.info(f"HandBrakeCLI CMD (extras): {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    logging.info(f"{output_file} | {out_dir} | {preset}")
    if result.returncode != 0:
        logging.error(f"Extra failed: {result.stderr}")
    else:
        logging.info("Extra processed successfully.")



def main(movie_root):
    title, year = get_movie_info(movie_root)
    rip_path = os.path.join(movie_root, "rip")
    plex_root = os.path.join(movie_root, "Plex Movie Files")
    if not os.path.isdir(rip_path):
        error_msg = f"ERROR: rip folder not found: {rip_path}"
        logging.error(error_msg)
        print(error_msg, file=sys.stderr)  # Print error to the console
        sys.exit(1)  # Exit with code 1 (generic error)
    movies = [f for f in os.listdir(rip_path) if f.lower().endswith(".mkv")]

    full_paths = [os.path.join(rip_path, f) for f in movies]
    logging.info(f"Rip path: {rip_path}")
    logging.info(f"MKV files found: {movies}")

    # Process main feature
    if full_paths:
        main_feature = identify_main_feature(full_paths)
        extras = [f for f in full_paths if f != main_feature]
        process_main_feature(main_feature, plex_root, title, year)
        os.makedirs(plex_root, exist_ok=True)
        user = getpass.getuser()
        uid = pwd.getpwnam(user).pw_uid
        gid = grp.getgrnam(user).gr_gid
        os.chown(plex_root, uid, gid)
        os.chmod(plex_root, 0o775)
    else:
        logging.warning(f"No MKV files in: {rip_path}")
        extras = []

    # Process extras in each Extras folder
    for extra in extras:
        extra_base = os.path.splitext(os.path.basename(extra))[0]
        assigned = False
        # Optionally, assign extras to folders based on name or some user convention
        for folder in EXTRA_FOLDERS:
            if folder.lower().replace(" ", "_") in extra_base.lower():
                out_dir = os.path.join(plex_root, folder)
                os.makedirs(out_dir, exist_ok=True)
                user = getpass.getuser()  # Should be 'jgordon'
                uid = pwd.getpwnam(user).pw_uid
                gid = grp.getgrnam(user).gr_gid
                os.chown(out_dir, uid, gid)
                os.chmod(out_dir, 0o775)
                process_extra(extra, out_dir, extra_base, folder.replace(" ", ""), PRESETS['extras'])
                assigned = True
                break
        if not assigned:
            # Default to "Other"
            out_dir = os.path.join(plex_root, "Other")
            os.makedirs(out_dir, exist_ok=True)  # <-- ensure created
            user = getpass.getuser()
            uid = pwd.getpwnam(user).pw_uid
            gid = grp.getgrnam(user).gr_gid
            os.chown(out_dir, uid, gid)
            os.chmod(out_dir, 0o775)
            process_extra(extra, out_dir, extra_base, "Other", PRESETS['extras'])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python handbrake_batch.py /path/to/<Movie Title (YYYY)>")
        sys.exit(1)
    movie_root_path = sys.argv[1]
    main(movie_root_path)
