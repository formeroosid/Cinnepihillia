# Cinnephillia

A pragmatic, ffmpeg-native media transcoding pipeline for cinephiles who rip their own optical media. Cinnephillia takes MakeMKV rips and produces clean, Plex-friendly libraries with consistent video quality, lossless primary audio, and predictable file naming.

It is opinionated by design: it does not try to be a universal transcoder, and it does not try to do online metadata matching. It does one thing well — turn a folder of MakeMKV rips into a tidy library — and stays out of your way.

## Features

- ffmpeg 8.x pipeline using `libx265` for Blu-ray and UHD encodes
- Resolution-based profile selection: SD/DVD, Blu-ray (1080p), and UHD (2160p HDR10)
- Single-track audio policy preserving DTS-HD MA losslessly when available
- First English PGS subtitle preserved when present
- Chapter markers preserved
- Sequential, deterministic TV episode naming, no metadata matching
- Suffix-driven movie extras placement using the Plex local-files convention
- Modular Python layout: `core/`, `movies/`, `tv/`, `shared/`, plus `utils/` shell helpers

## Why software x265

Cinnephillia uses software `libx265` for Blu-ray and UHD because, on real-world projector setups at typical viewing distances, the compression efficiency advantage over `hevc_vaapi` is visible and meaningful. SD/DVD continues to use VAAPI because the source resolution does not benefit from slow software encoding.

## Profiles

| Profile | Source | Encoder | Pixel format | Rate control | Color signaling |
|---|---|---|---|---|---|
| `sd` | DVD / SD broadcast | `hevc_vaapi` | `nv12` | `-b:v 5M` | n/a |
| `bluray` | 1080p Blu-ray | `libx265` | `yuv420p` | `-crf 20`, `preset slow` | BT.709 limited range |
| `4k` (UHD) | 2160p HDR10 Blu-ray | `libx265` | `yuv420p10le` | `-crf 23`, `preset slow` | BT.2020 / SMPTE ST 2084 / HDR10 |

Profile selection is automatic based on detected video resolution. A single audio track is selected with this priority: English DTS-HD MA → any DTS English → first audio. The first English PGS subtitle is included if present. Chapters are always preserved.

## Requirements

- Python 3.10+
- A modern ffmpeg build with `libx265`, `hevc_vaapi`, and `hevc_vulkan` enabled. The author runs a custom ffmpeg 8.1 build under `/usr/local`.
- `ffprobe` available on `PATH`
- A VAAPI-capable GPU node at `/dev/dri/renderD128` for the SD profile
- MakeMKV for ripping discs to MKV

## Installation

```bash
git clone https://github.com/formeroosid/Cinnephillia.git
cd Cinnephillia
```

There is no `setup.py` or PyPI package; Cinnephillia is run directly from the project root.

## Usage

```bash
# A single movie
python3 Cinnephillia.py "/mnt/bigbrother/Movies/Lincoln (2012)" \
    --type movie --mode feature

# A movie plus its extras (after annotating extra files — see below)
python3 Cinnephillia.py "/mnt/bigbrother/Movies/Lincoln (2012)" \
    --type movie --mode both

# A TV series, ripping all discs and rendering all episodes
python3 Cinnephillia.py "/mnt/bigbrother/TV/Star Trek - Strange New Worlds{tvdb-382389}/" \
    --mode both --type tv \
    --series-name "Star Trek - Strange New Worlds"
```

`--mode` is one of `feature`, `extras`, or `both`. `--type` is `movie` or `tv`.

## Movie extras workflow

Movies support a fully automated extras pipeline driven by filename suffixes. The workflow is:

1. **Rip the disc with MakeMKV** into the title's `rip/` directory. All titles land as `_t00.mkv`, `_t01.mkv`, etc., with no semantic meaning attached.
2. **Review and annotate.** Identify which rips are extras and rename them in-place using a recognized Plex local-files suffix. Files without a suffix are treated as the feature.
3. **Run Cinnephillia with `--mode extras` or `--mode both`.** The pipeline parses each filename's suffix, encodes the file using the appropriate resolution profile, writes the encoded MKV to `process/staging/`, and creates a symlink in the matching `Plex Movie Files/<Category>/` folder.

### Suffix → folder mapping

| Suffix | Plex Movie Files folder |
|---|---|
| `--behindthescenes` | `Behind The Scenes/` |
| `--deleted` | `Deleted Scenes/` |
| `--featurette` / `-featurettes` | `Featurettes/` |
| `--interview` | `Interviews/` |
| `--scene` | `Scenes/` |
| `--short` | `Shorts/` |
| `--trailer` | `Trailers/` |
| `--other` | `Other/` |
| (none) | feature output at the title root |

Extras go through the same `select_preset()` resolution check as features, so a 1080p extra encodes with the `bluray` software x265 profile, a 2160p extra encodes with the UHD profile, and an SD extra goes through VAAPI. The single-audio policy and PGS subtitle handling apply uniformly to features and extras alike.

### TV extras

The TV pipeline currently handles only sequential episode naming. To add TV extras, encode the extras through Cinnephillia (or by hand) into `process/staging/` and create the symlinks under the series-level `Plex Movie Files/Behind The Scenes/`, `Deleted Scenes/`, `Featurettes/`, etc. yourself. The movie suffix-driven placement does not run on TV titles.

## Directory conventions

Cinnephillia expects each title to live in its own folder. Inside that folder, three subdirectories define the lifecycle: `rip`, `process`, and `Plex Movie Files`.

### TV series

For a TV series, Cinnephillia walks `rip/SXXDXX/` directories in lexical order and renders each MKV through the appropriate profile into `process/staging/`. It then creates symlinks under `Plex Movie Files/Season XX/` named sequentially as `<series name> SXXEXX_.mkv`. Episode numbers are assigned in disc-then-title order across the entire season, with no metadata matching and no duration filtering. The trailing underscore is intentional and left for hand annotation during review.

A series folder looks like this (abbreviated):

```
Star Trek - Strange New Worlds{tvdb-382389}/
├── Plex Movie Files
│   ├── Behind The Scenes
│   │   ├── Season 3 - Gag Reel.mkv -> .../process/staging/S3D1/...t08.mkv
│   │   └── ...
│   ├── Deleted Scenes
│   │   ├── Season3 - Deleted Scenes.mkv -> .../process/staging/S3D1/...t00.mkv
│   │   └── ...
│   ├── Featurettes
│   │   ├── Exploring New Worlds -featurettes.mkv -> .../process/staging/S3D3/...t01.mkv
│   │   └── ...
│   ├── Interviews
│   ├── Other
│   ├── Scenes
│   ├── Season 1
│   │   ├── Star Trek - Strange New Worlds S01E01_.mkv -> .../process/staging/S1D1/...t00.mkv
│   │   ├── Star Trek - Strange New Worlds S01E02_.mkv -> .../process/staging/S1D1/...t01.mkv
│   │   ├── ...
│   │   └── Star Trek - Strange New Worlds S01E10_.mkv -> .../process/staging/S1D3/...t01.mkv
│   ├── Season 2
│   │   ├── Star Trek - Strange New Worlds S02E01_.mkv -> .../process/staging/S2D1/...t00.mkv
│   │   ├── ...
│   │   └── Star Trek - Strange New Worlds S02E10_.mkv -> .../process/staging/S2D4/...t00.mkv
│   ├── Shorts
│   └── Trailers
├── process
│   └── staging
│       ├── S1D1
│       │   ├── Star Trek- Strange New Worlds - Season 1 (Disc 1)_t00.mkv
│       │   └── ...
│       ├── S1D2
│       ├── ...
│       └── S2D4
│           └── Star Trek- Strange New Worlds - Season 2 (Disc 4)_t00.mkv
└── rip
    ├── S1D1
    │   ├── Star Trek- Strange New Worlds - Season 1 (Disc 1)_t00.mkv
    │   └── ...
    ├── ...
    └── S2D4
        └── Star Trek- Strange New Worlds - Season 2 (Disc 4)_t00.mkv
```

The folder name may include Plex/TVDB-style hints such as `{tvdb-382389}` for indexer matching. Cinnephillia does not parse these — they are for Plex.

### Movies

Movie titles use the same three-subdirectory pattern, but the `Plex Movie Files/` layout is flat rather than season-based. After ripping, files in `rip/` may be renamed with extras suffixes before encoding:

```
Lincoln (2012)/
├── rip/
│   ├── Lincoln (2012)_t00.mkv                              # the feature, untagged
│   ├── Making Of--featurette.mkv                           # tagged as a Featurette
│   ├── Deleted Scene 1--deleted.mkv                        # tagged as a Deleted Scene
│   └── Trailer--trailer.mkv                                # tagged as a Trailer
├── process/
│   └── staging/
│       ├── Lincoln (2012).mkv
│       ├── Making Of--featurette.mkv
│       ├── Deleted Scene 1--deleted.mkv
│       └── Trailer--trailer.mkv
└── Plex Movie Files/
    ├── Lincoln (2012).mkv -> ../process/staging/Lincoln (2012).mkv
    ├── Behind The Scenes/
    ├── Deleted Scenes/
    │   └── Deleted Scene 1--deleted.mkv -> ../../process/staging/Deleted Scene 1--deleted.mkv
    ├── Featurettes/
    │   └── Making Of--featurette.mkv -> ../../process/staging/Making Of--featurette.mkv
    ├── Interviews/
    ├── Other/
    ├── Scenes/
    ├── Shorts/
    └── Trailers/
        └── Trailer--trailer.mkv -> ../../process/staging/Trailer--trailer.mkv
```

### Extras folders

The `Behind The Scenes/`, `Deleted Scenes/`, `Featurettes/`, `Interviews/`, `Other/`, `Scenes/`, `Shorts/`, and `Trailers/` folders match Plex's recognized extras categories. For movies these are populated automatically from filename suffixes; for TV you create the symlinks during review.

## Utility scripts (`utils/`)

Cinnephillia ships a small set of shell helpers under `utils/` that handle the "after the encode" side of things — staging the finished `Plex Movie Files/` trees onto the Plex server and triggering library refreshes. They are intentionally separate from the Python pipeline so you can run them independently from any host.

| Script | Purpose                                                                                                                                                                                                                                                                                                                                                                                           |
|---|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `utils/copy_plex_movies.sh` | Walks a Movies root (or a single movie directory), and for each title rsyncs its `Plex Movie Files/` contents into a clean destination tree organized by movie title. Run from the staging machine; takes `SOURCE_DIR` and `DEST_DIR` as arguments.                                                                                                                                               |
| `utils/copy_plex_tv.sh` | The TV-side counterpart to `copy_plex_movies.sh`. Accepts either a TV root containing many series or a single series directory, and rsyncs each series' `Plex Movie Files/` contents into a per-series subdirectory of the destination. Uses `rsync -rltL` so symlinked episode files copy as real data.                                                                                          |
| `utils/cp2movie.sh` | Run from a movie title's working directory on the Plex server (the script enforces `hostname == lumpy` _Update for your own Plex hostname_). Rsyncs the current title into `/data/Media/Movies/`, applies `jgordon:plex` _(update for your username)_ ownership and Plex-friendly permissions, then triggers a Movies-library metadata refresh via the local Plex API. Supports `-n` for a dry run. |
| `utils/cp2tv.sh` | The TV-side counterpart to `cp2movie.sh`. Rsyncs the current series directory into `/data/Media/TV Shows/` on Lumpy with the same ownership and chmod policy, then triggers a TV-library refresh against the local Plex API. Supports `-n` for a dry run.                                                                                                                                         |

The `copy_plex_*` scripts are the portable, "stage anywhere" path; the `cp2*` scripts are the opinionated deployment path that also kicks Plex.

> Note: `cp2movie.sh` and `cp2tv.sh` read `PLEX_TOKEN` from the environment and assume Plex is reachable on `127.0.0.1:32400`. Set `PLEX_TOKEN` before running, and confirm the section IDs (`1` for Movies, `2` for TV) match your install.

## Design choices worth knowing

- **No metadata matching.** TV episodes are renamed sequentially across discs, in disc-then-title order. Variable runtimes, "play all" titles, and bonus features are not filtered out automatically. You review the `Plex Movie Files/Season XX/` folder by hand and rename or remove what you don't want.
- **Single primary audio.** Commentary tracks and lossy DTS cores are dropped by default. The DTS-HD MA primary is copied losslessly. If you want to preserve commentary, modify the audio mapping in `core/ffmpeg_runner.py`.
- **Symlinks, not copies.** `Plex Movie Files/` contains symlinks into `process/staging/`. This keeps the Plex view tidy while the encoded files live exactly once on disk.
- **Suffix-driven extras for movies.** Annotating MakeMKV rips with `--featurette`, `--deleted`, etc. is the contract that drives automatic Plex-folder placement. No config files, no GUI.
- **Trailing underscore in episode filenames.** `<series> SXXEXX_.mkv` leaves an obvious place for hand annotation during review without breaking Plex matching.

## Project layout

```
Cinnephillia/
├── Cinnephillia.py            # CLI entry point and dispatcher
├── core/
│   ├── ffmpeg_profiles.py     # Profile dicts and select_preset()
│   ├── ffmpeg_runner.py       # encode_with_profile() and helpers
│   ├── media_analyzer.py      # detect_resolution() and probe helpers
│   └── ...
├── movies/
│   └── movie_pipeline.py
├── tv/
│   ├── disc_parser.py
│   └── tv_pipeline.py
├── shared/
│   └── ...
└── utils/
    ├── copy_plex_movies.sh    # Stage movies into a clean destination tree
    ├── copy_plex_tv.sh        # Stage TV series into a clean destination tree
    ├── cp2movie.sh            # Push current movie to Lumpy + refresh Plex
    └── cp2tv.sh               # Push current series to Lumpy + refresh Plex
```

## Status

Cinnephillia is feature-complete for the author's home theater workflow and is considered finalized. Issues and PRs are welcome at https://github.com/formeroosid/Cinnephillia, but the scope is intentionally small.

## License

Cinnephillia is released under the [MIT License](LICENSE). © 2026 formeroosid.
