# Cinnephillia

Cinnephillia is a Python-based media workflow project for organizing, inspecting, and transcoding video files for a home theater library. A good README should explain what the project does, what it requires, and how to get started using instructions that match the repository's current state.

## Status

This project is actively evolving. The repository structure, entry points, and dependency management may continue to change as the codebase is refactored and stabilized.

## What it does

Cinnephillia is intended to support local media-library workflows such as scanning media, applying FFmpeg-based transcode profiles, and organizing code into reusable modules instead of one-off scripts. A useful project README should focus on the purpose, setup, and usage of the project before diving into development details.

## Current setup

At the moment, the project should be documented based on what actually exists in the repository. Installation instructions should not claim that `requirements.txt` or another dependency file exists unless it is really present and maintained.

### Prerequisites

- Python 3.10 or newer
- FFmpeg installed and available on `PATH`
- FFprobe installed and available on `PATH`
- Git
- Linux is recommended if the project depends on VAAPI or similar hardware acceleration

### Clone the repository

```bash
git clone git@github.com:formeroosid/Cinnepihillia.git
cd Cinnephiilia
```

### Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

This creates an isolated Python environment for the project. A virtual environment is separate from a `.env` file and separate from dependency files like `requirements.txt` or `pyproject.toml`.

### Install Python packages

The repository does **not** currently document a finalized dependency file. Because of that, do not use `pip install -r requirements.txt` unless that file has been added to the project.

Until dependency management is finalized, install the packages actually required by the modules or scripts you are running. Once the dependency list is stable, add either:

- a `requirements.txt` file for pinned installs, or
- a `pyproject.toml` file for modern Python project metadata and dependency management.

## Configuration

If the project needs machine-specific settings such as library paths, output directories, or API keys, those can be stored in a `.env` file. A `.env` file is for runtime configuration values; it does **not** install Python dependencies.

Example `.env`:

```env
MEDIA_ROOT=/path/to/media
OUTPUT_ROOT=/path/to/output
LOG_LEVEL=INFO
```

Only include this section if the code actually reads environment variables.

## Usage

Replace the examples below with the real commands used by the current codebase.

```bash
source .venv/bin/activate
python main.py
```

If the project is script-driven, document the actual scripts instead:

```bash
python scripts/scan_library.py
python scripts/transcode_item.py --input /path/to/movie.mkv
```

Effective READMEs use short, copy-paste-ready examples so that a new user can quickly see how to run the project.[cite:610][cite:641]

## Project structure

Update this section to match the repository as it exists today.

```text
Cinnephillia/
├── core/                  # Core logic
├── ffmpeg_profiles/       # Encode/transcode presets
├── scripts/               # Utility scripts or entry points
├── tests/                 # Tests
├── README.md              # Project overview and setup
└── ...
```

Directory maps help readers understand where to look next, especially in evolving Python projects.[cite:610][cite:573]

## Development notes

- Keep debug prints temporary and remove them once issues are resolved.
- Avoid committing log files, local virtual environments, or IDE-specific project files.
- Use feature branches and pull requests for larger changes.
- Keep documentation aligned with the actual repository state.

Recommended `.gitignore` entries:

```gitignore
.venv/
.idea/
*.log
__pycache__/
```

## Dependency management plan

When the Python package list becomes stable, create one of the following and then update this README accordingly:

### Option A: `requirements.txt`

If the project is mainly an application and you want a simple install path, generate and maintain a `requirements.txt` file.

Example:

```bash
source .venv/bin/activate
pip freeze > requirements.txt
```

### Option B: `pyproject.toml`

If the project is moving toward a more modern Python structure, use `pyproject.toml` for metadata and dependency management.

## License

Choose a license and add a `LICENSE` file at the repository root. READMEs are typically most useful when they clearly state setup, usage, and licensing terms in one place.
