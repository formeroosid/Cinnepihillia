# Cinnephillia

A pragmatic, ffmpeg-native media transcoding pipeline for cinephiles who rip their own optical media. Cinnephillia takes MakeMKV rips and produces Plex-friendly libraries with predictable naming, copied audio, and selectable video-encoding backends. It does not perform online metadata matching.

## Features

- Native backend (default): software `libx265` for HD/UHD and `hevc_vaapi` for SD.
- Optional NVIDIA `hevc_nvenc` backend for movie features and extras.
- Resolution-based profile selection for movie features.
- First audio track copied losslessly by default; `--preserve-all-audio` copies every audio track.
- First subtitle identified as English or untagged by the shared probe is selected and copied; the selector is not restricted to PGS. Inspect dry-run stream mappings.
- Chapter mapping, including chapter metadata, through the shared runner.
- Optional UHD Dolby Vision RPU conversion/injection targeting Profile 8.1, with Matroska HDR/color-property preservation and verification.
- Movie extras placement by category-name suffix; sequential TV episode naming without metadata matching.

See [NVIDIA/NVENC guide](docs/NVENC.md) for requirements, settings, limitations, and acceptance testing.

## Encoding backends and profiles

`--encoder native` is the default. `--encoder nvenc` is opt-in and supported only with `--type movie`; TV mode rejects it. Native HD/UHD encoding remains software x265. NVENC changes video encoding, not the shared audio/subtitle/chapter handling. GPU decoding is not enabled by this option.

| Backend | Profile | Video encoder | Format | Rate control | Color options |
|---|---|---|---|---|---|
| native | `sd` | `hevc_vaapi` | nv12 with hwupload | 5M bitrate | No explicit color override |
| native | `bluray` | `libx265` | yuv420p | CRF 20, slow | BT.709 |
| native | `4k` | `libx265` | yuv420p10le | CRF 23, slow | BT.2020/PQ, x265 HDR10 options |
| nvenc | `sd` | `hevc_nvenc` Main | nv12 | VBR, CQ 20, bitrate 0 | No explicit color override |
| nvenc | `bluray` | `hevc_nvenc` Main | nv12 | VBR, CQ 20, bitrate 0 | BT.709 |
| nvenc | `4k` | `hevc_nvenc` Main10 | p010le | VBR, CQ 23, bitrate 0 | Limited-range BT.2020/PQ |

All NVENC profiles select GPU 0, preset P6, HQ tuning, and passthrough frame timing. CQ values are starting settings, not equivalents of x265 CRF values.

Movie features select `4k` when width is at least 3840 or height at least 2160; otherwise `sd` when width is at most 720 or height at most 576; otherwise `bluray`. Unknown dimensions fall back to `bluray`. This is resolution-based selection, not HDR detection or tone mapping: inspect the profile before processing SDR UHD or other atypical sources.

Movie extras always use the `bluray` profile with the chosen backend, regardless of source dimensions. The legacy `extras_720p` name is only a log label; it does not request 720p scaling. Extras do not engage the UHD Dolby Vision path.

## Requirements

- Python 3.10+.
- `ffmpeg` and `ffprobe` on `PATH`; the project targets a modern ffmpeg 8.x workflow.
- Encoder support for the selected backend: `libx265` for native HD/UHD, or `hevc_vaapi` and a usable `/dev/dri/renderD128` for native SD.
- For NVENC: a compatible NVIDIA GPU/driver and an ffmpeg build with usable `hevc_nvenc` support. UHD needs Main10 support. See the [NVENC checks](docs/NVENC.md#prerequisites-and-checks).
- For Dolby Vision: `dovi_tool` and `mkvmerge` (MKVToolNix) on `PATH`, plus a source with detected Dolby Vision metadata.
- MakeMKV or another source of suitable MKV rips.

Each real encode first attempts a one-frame encoder preflight using the actual video arguments. A nonzero exit or recognized option-parsing error stops that encode. A dry run skips this hardware check.

## Installation

```bash
git clone https://github.com/formeroosid/Cinnepihillia.git
cd Cinnepihillia
```

There is no `setup.py` or PyPI package; run from the project root. NVENC documentation describes the feature branch associated with PR #10; it does not imply that the branch has been merged into `master`.

## Usage

```bash
# Native movie feature (default backend)
python3 Cinnephillia.py "/path/to/Lincoln (2012)" \
    --type movie --mode feature

# Preview NVIDIA movie processing with every audio track
python3 Cinnephillia.py "/path/to/Movie Title (YYYY)" \
    --type movie --mode both --encoder nvenc \
    --preserve-all-audio --dolby-vision auto --dry-run

# Require Dolby Vision preservation for an applicable UHD feature
python3 Cinnephillia.py "/path/to/Movie Title (YYYY)" \
    --type movie --mode feature --encoder nvenc \
    --preserve-all-audio --dolby-vision p81 --dry-run

# TV retains the native backend
python3 Cinnephillia.py "/path/to/Series Title" \
    --type tv --series-name "Series Title"
```

| Option | Behavior |
|---|---|
| `--type movie|tv` | Default: movie |
| `--mode feature|extras|both` | Movie processing selection; default: both |
| `--encoder native|nvenc` | Default: native; NVENC is movie-only |
| `--preserve-all-audio` | Copy all audio tracks rather than only the first |
| `--dolby-vision auto|off|p81|p76` | Default: auto; only applies to `4k` profiles |
| `--dry-run` | Preview processing commands; skips encoding, preflight, RPU extraction/injection, and HDR remux verification |

Dry runs still probe inputs and may create output/scratch directories. They are not a substitute for hardware or playback testing. Inspect paths and mappings in an isolated test root before removing `--dry-run`. Encoding uses ffmpeg `-y`; do not test against valuable existing output files.

## Dolby Vision and HDR metadata

For an applicable UHD profile, `auto` enables preservation when the source has detected Dolby Vision metadata and both external tools are available. If a required tool is absent it warns and proceeds without Dolby Vision. Forced `p81`/`p76` modes fail when the source metadata or tools are missing. `off` disables preservation. `p76` currently warns and converts to Profile 8.1; enhancement-layer preservation is not implemented.

The pipeline:

1. Extracts the RPU using `dovi_tool -m 2 extract-rpu`.
2. Encodes the base video into `.cinne-dv-*/encode_hdr10.mkv` beside the output.
3. Reads video packet counts and frame rate through structured ffprobe JSON and refuses injection if RPU/video counts differ.
4. Reads available HDR/color track properties from the encoded MKV using `mkvmerge -J`.
5. Extracts HEVC, injects the RPU, and remuxes with copied audio, subtitles, chapters, and discovered HDR/color properties.
6. Requires detected Dolby Vision Profile 8 and verifies the copied HDR/color properties.

HDR values are read from the encoded MKV, not hardcoded or reconstructed from missing source metadata. Preserving Matroska track properties does not insert static HDR SEI messages into elementary HEVC. Automated DV verification currently checks Profile 8, not specifically compatibility ID 1; acceptance testing must check Profile 8.1 and playback separately.

On a handled post-encode Dolby Vision failure, the runner removes the final output and retains the encoded HDR10 MKV/RPU scratch directory for inspection. Earlier extraction/encoding failures have different cleanup behavior. Allow ample free space beside the output: injection/remux can retain an encoded MKV, raw HEVC copies, and the final MKV simultaneously.

## Movie layout and extras

The largest MKV in a movie's `rip/` directory is assumed to be the main feature. All other MKVs are extras, including in extras-only mode. This is a size heuristic, not title recognition.

Movie processing writes real files directly under `Plex Movie Files/`; it does not use the TV staging/symlink workflow.

```text
Movie Title (YYYY)/
├── rip/
│   ├── Feature_t00.mkv
│   ├── Making Of-Featurettes.mkv
│   ├── Deleted Scene-Deleted Scenes.mkv
│   └── Preview-Trailers.mkv
└── Plex Movie Files/
    ├── Movie Title (YYYY).mkv
    ├── Featurettes/
    │   └── Making Of.mkv
    ├── Deleted Scenes/
    │   └── Deleted Scene.mkv
    └── Trailers/
        └── Preview.mkv
```

Recognized category names are `Behind The Scenes`, `Deleted Scenes`, `Featurettes`, `Interviews`, `Other`, `Shorts`, and `Trailers`. Matching is case-insensitive; spaces within category names may be spaces, underscores, or hyphens. A space, underscore, or hyphen separates the title from the category. The matched category suffix is removed from the output filename. Unmatched extras retain their basename and go under `Other/`.

Use full category names, as in the example. The current matcher does not implement the older documented shorthand suffixes such as `--featurette`, `--deleted`, or `--trailer`; there is no `Scenes` category in the current movie list.

## TV layout and review

The TV workflow uses `rip/`, `process/staging/`, and `Plex Movie Files/Season XX/`. It assigns episode numbers in disc/title order and creates Plex-facing symlinks to staged encodes. Episode names have the form `<series name> SXXEXX_.mkv`; the trailing underscore leaves room for manual annotation.

Review episode order and bonus titles manually: there is no online metadata matching or automatic semantic identification. Folder hints such as `{tvdb-382389}` are for Plex, not parsed by Cinnephillia. Movie category matching does not run for TV extras; arrange those separately.

## Utility scripts

| Script | Purpose |
|---|---|
| `utils/copy_plex_movies.sh` | Copy movie `Plex Movie Files/` trees to a destination organized by title; accepts source and destination directories |
| `utils/copy_plex_tv.sh` | Copy TV trees; dereference staged episode symlinks into real destination files |
| `utils/cp2movie.sh` | Opinionated Plex-host movie deployment and library refresh; supports `-n` |
| `utils/cp2tv.sh` | Opinionated Plex-host TV deployment and library refresh; supports `-n` |

Review scripts before use. The `cp2*` helpers contain author-specific hostname, destination, ownership, and library-section assumptions. They read `PLEX_TOKEN` from the environment and expect Plex on `127.0.0.1:32400`. Adapt these values to your installation.

## Tests and acceptance status

```bash
python3 -m unittest discover -s tests -p 'test_dolby_vision.py' -v
python3 -m unittest discover -s tests -p 'test_encoder_backend.py' -v
```

The unit tests cover mocked Dolby Vision/HDR operations and hardware-independent backend settings; they do not establish playback quality or GPU availability.

A full-length Chinatown test on Larry completed NVENC encoding and Dolby Vision injection but exposed HDR container metadata loss during remux. A manual container repair restored the reported properties. PR #10 now contains the automated preservation fix; a clean-checkout test run and short hardware regression of that committed fix remain pending. HD/SD NVENC, extras, and playback/image-quality acceptance also remain pending. See the [NVENC acceptance checklist](docs/NVENC.md#acceptance-checklist).

## Project layout

```text
Cinnepihillia/
├── Cinnephillia.py
├── core/                 # profiles, shared runner, probing, Dolby Vision
├── movies/               # feature and extras routing
├── tv/                   # TV processing and naming
├── shared/
├── tests/
├── docs/NVENC.md
└── utils/                # deployment helpers
```

## Scope and license

The scope is intentionally small: local media processing for a home-theater workflow, not universal transcoding or metadata management. Report issues and review changes in the repository.

Cinnephillia is released under the [MIT License](LICENSE). © 2026 formeroosid.
