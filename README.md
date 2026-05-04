# Cinnephillia

Cinnephillia is a Python-based media processing and library-management project built for a home theater workflow. It is designed to help organize, inspect, and transcode media into playback-friendly formats while keeping the process reproducible and maintainable.

## Overview

Cinnephillia focuses on local media workflows, including FFmpeg-driven transcoding, branch-based development, and a structure intended to grow into a maintainable application for home-theater media management.

## Features

- Manage and prepare media for a home theater library.
- Run FFmpeg-based transcoding workflows.
- Organize code around reusable modules instead of one-off scripts.
- Support development through Git branches and pull requests.
- Provide a foundation for future automation, metadata handling, and playback optimization.

## Goals

- Standardize media processing tasks.
- Reduce manual command-line repetition.
- Preserve a clear project structure as the codebase grows.
- Make the workflow understandable for future contributors and for future you.

## Project Structure

```text
Cinnephillia/
├── core/                  # Core application logic
├── ffmpeg_profiles/       # Encoding/transcoding profiles and presets
├── scripts/               # Utility or entry-point scripts
├── tests/                 # Automated tests
├── README.md              # Project documentation
└── ...
```

## Requirements

- Python 3.10+
- FFmpeg installed and available on `PATH`
- FFprobe installed and available on `PATH`
- Git for version control
- A Linux environment is recommended if the project relies on VAAPI or similar hardware-acceleration paths

## Installation

```bash
git clone git@github.com:formeroosid/Cinnepihillia.git
cd Cinnephiilia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Example development workflow:

```bash
source .venv/bin/activate
python main.py
```

Example script-oriented workflow:

```bash
python scripts/scan_library.py
python scripts/transcode_item.py --input /path/to/movie.mkv
```

If the real entry points differ, replace these examples with the exact commands used in the project. Concrete usage examples make a README substantially more useful for both users and collaborators.[web:569][web:573]

## FFmpeg Notes

This project is intended for media transcoding and related automation, and FFmpeg is a standard tool for Python-based transcoding workflows.

Suggested additions for this section:

- Supported input containers and codecs
- Supported output targets
- Hardware acceleration requirements
- Subtitle and audio-stream handling rules
- Failure and logging behavior

## Development

Recommended day-to-day workflow:

```bash
git checkout -b feature/my-change
# make changes
git add .
git commit -m "Describe the change"
git push -u origin feature/my-change
```

Then open a pull request on GitHub to merge into `master`.

## Roadmap

Potential next steps for Cinnephillia:

- Add automatic metadata inspection and reporting
- Add a config file for paths, profiles, and output rules
- Add a test suite for media-selection logic
- Add logging configuration and error-reporting standards
- Add documentation for library layout and naming conventions
- Add containerization or service scripts if the app becomes long-running

## Contributing

Contributions should follow the existing project structure, keep modules focused, and avoid unnecessary debug output in committed code. Open an issue or pull request for significant changes, and include enough context for the change to be reviewed quickly.
