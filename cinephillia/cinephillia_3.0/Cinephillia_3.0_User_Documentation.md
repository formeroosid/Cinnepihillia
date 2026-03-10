# Cinephillia 3.0 — User Documentation

## Overview

Cinephillia 3.0 is a Python-based media pipeline for ripping, encoding, renaming, and organizing TV series (and eventually movies) into a Plex-ready library structure. It chains together MakeMKV (ripping), HandBrakeCLI (encoding), and FileBot (renaming) into an automated workflow.

---

## Prerequisites

### Required Software

| Tool | Install Method | Purpose |
|------|---------------|---------|
| **Python 3.x** | System package | Pipeline runtime |
| **MakeMKV** | Flatpak/native | Disc ripping to MKV |
| **HandBrakeCLI** | Flatpak (`fr.handbrake.ghb`) | Video encoding |
| **FileBot** | Snap (`/snap/bin/filebot`) | Episode renaming via AMC script |

### FileBot Snap Permissions

FileBot installed via snap is sandboxed and **cannot access `/tmp`** or arbitrary filesystem paths. Grant access to mounted drives:

```bash
sudo snap connect filebot:removable-media
```

> **Important:** Always use paths under your home directory (`~/`) or `/mnt`/`/media` for staging and output directories. `/tmp` paths will silently fail with FileBot snap.

---

## Project Structure

```
cinephillia_3.0/
├── cinephillia/
│   ├── core/
│   │   ├── detection.py          # Audio track detection & argument building
│   │   ├── handbrake_profiles.py # Preset selection & overrides
│   │   └── handbrake_runner.py   # HandBrakeCLI execution
│   ├── shared/
│   │   └── file_ops.py           # Directory creation & permissions
│   └── tv/
│       ├── cli.py                # Command-line interface
│       ├── disc_parser.py        # MKV title discovery from rip input
│       ├── episode_classifier.py # Classifies titles as episodes vs extras
│       ├── filebot_renamer.py    # FileBot AMC & direct rename wrappers
│       ├── inventory.py          # Pre/post-flight inventory reporting
│       └── tv_pipeline.py        # Main TV series processing pipeline
└── profiles/
    └── SD_TV_-_x265_8bit_CRF22.json  # HandBrake encoding presets
```

---

## Usage

### Basic Command

```bash
python3 -m cinephillia.tv.cli process \
  --input ~/media/rip \
  --staging ~/media/staging \
  --output ~/media/plex \
  --series "Quantum Leap" \
  --encode sd
```

### CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Path to ripped MKV files (e.g., from MakeMKV) |
| `--staging` | Yes | Working directory for encoded files |
| `--output` | Yes | Final Plex library root directory |
| `--series` | Yes | Series name for matching and inventory |
| `--encode` | No | Encoding profile override (`sd`, etc.). Auto-detected from resolution if omitted. |
| `--dry-run` | No | Show inventory report without encoding or renaming |

---

## Pipeline Phases

### Phase 0: Pre-flight Inventory
- Scans the `--input` directory for MKV titles using `disc_parser`
- Classifies titles into **episodes** and **extras** based on duration
- Prints an inventory report

### Phase 1: Encode
- For each episode, detects audio tracks and builds appropriate audio arguments (AAC + DTS passthrough)
- Selects a HandBrake preset based on source resolution, or uses the `--encode` override
- Encodes via HandBrakeCLI (flatpak) into the staging directory
- **Skips files that already exist** in staging (resume-safe)

### Phase 2: Rename
- Runs FileBot's AMC (Automated Media Center) script against the staging directory
- Matches episodes against TheMovieDB/TheTVDB
- Copies (duplicates) files into Plex-structured output: `Series Name/Season X/Series Name - S01E01 - Episode Title.mkv`

### Phase 3: Post-flight Inventory
- Scans the output directory for renamed files
- Prints a final inventory report

---

## Encoding Profiles

Profiles are stored as HandBrake JSON presets in the `profiles/` directory.

| Profile Flag | Preset Name | Description |
|-------------|-------------|-------------|
| `sd` | SD TV - x265 8bit CRF22 | Standard definition TV content, x265 codec |

When `--encode` is omitted, the pipeline auto-selects a preset based on the source video's resolution (`width × height`).

### Audio Handling
- Track 1: AAC (compatibility)
- Track 2: DTS passthrough (quality)
- All subtitles are preserved
- Output container: MKV

---

## Input Directory Structure

Ripped discs should be organized by season and disc:

```
~/media/rip/
├── S1D1/
│   ├── QUANTUM LEAP SEASON 1 DISC 1_t00.mkv
│   ├── QUANTUM LEAP SEASON 1 DISC 1_t01.mkv
│   └── ...
├── S1D2/
│   └── ...
└── S2D1/
    └── ...
```

The `SxDx` folder naming convention helps the classifier and FileBot with season matching.

---

## Output Structure (Plex-Ready)

```
~/media/plex/
└── Quantum Leap/
    └── Season 1/
        ├── Quantum Leap - S01E01 - July 13th, 1985.mkv
        ├── Quantum Leap - S01E02 - Star-Crossed.mkv
        └── ...
```

---

## Troubleshooting

### FileBot: "output folder must exist and must be a writable directory"
- Ensure the output directory exists before running the pipeline
- Ensure the path is accessible to the FileBot snap (use `~/` or `/mnt` paths, not `/tmp`)

### FileBot: "No files selected for processing"
- Check for a stale `amc_exclude.txt` in the staging directory — delete it and retry
- Verify the MKV filename contains enough metadata for FileBot to match (series name, season info)

### Pipeline re-encodes files that already exist
- The encode-skip logic checks for `out_path.exists() and out_path.stat().st_size > 0`
- Ensure the staging path structure matches: `staging/S1D1/filename.mkv`

### HandBrakeCLI can't access files
- HandBrake runs via flatpak and requires `--filesystem` flags for each path
- The pipeline handles this automatically via `handbrake_runner.py`

### PyCharm "Unresolved reference" warnings
- Right-click the `cinephillia_3.0` directory → **Mark Directory as** → **Sources Root**

---

## Known Limitations

- **Single-title test only** — the pipeline has been validated with one episode per disc; multi-episode disc splitting needs further testing
- **FileBot snap sandbox** — cannot access `/tmp` or paths outside `~/`, `/mnt`, `/media`
- **No movie pipeline yet** — only TV series processing is implemented
- **AMC database selection** — FileBot AMC chooses its own metadata source (typically TheMovieDB); this may differ from direct `-rename` mode which uses TheTVDB

---

*Cinephillia 3.0 — Built for the home theater enthusiast who wants full control over their media library.*
