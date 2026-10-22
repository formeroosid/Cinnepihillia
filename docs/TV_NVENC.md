# TV NVENC and Dolby Vision

This guide applies to the `feat/tv-nvenc` branch. It supersedes the movie-only NVENC restrictions in the existing README/NVENC guide for this branch. It does not mean the change has been merged or hardware-tested.

## Entry points

Both entry points accept `--encoder native|nvenc` and `--dolby-vision auto|off|p81|p76`. Defaults remain native/auto. NVENC reuses the movie profiles: GPU 0, P6/HQ, VBR, CQ 23/Main10/p010le for UHD and CQ 20/Main/nv12 for HD/SD. GPU decoding and HDR10+ preservation are not added.

For a newly encoded UHD episode, p81 requires detected source DV plus dovi_tool and mkvmerge; p76 currently converts to P8.1. Non-UHD profiles do not engage DV, even in forced modes. The shared helper preserves/verifies discovered HDR container properties; that is not insertion of static HDR SEI into raw HEVC.

## Isolated first test

On Larry, rip one confirmed episode to this proposed isolated root; retain its `_tNN.mkv` filename:

```text
/mnt/bigbrother/TV_test/Strange New Worlds S3 DV test/
    rip/S03D01/Episode_t00.mkv
```

Do not include extras or play-all titles. The main CLI includes all recognized titles and numbers them by season/disc/title order, not episode identity.

```bash
cd "$HOME/Cinnephiilia"
ROOT="/mnt/bigbrother/TV_test/Strange New Worlds S3 DV test"

# Inventory only: does not run preflight, profile selection or DV planning.
python3 Cinnephillia.py "$ROOT" --type tv \
    --series-name "Star Trek - Strange New Worlds" \
    --encoder nvenc --dolby-vision p81 --preserve-all-audio --dry-run

# Run only after inspecting the source and tally; processes the full input.
python3 Cinnephillia.py "$ROOT" --type tv \
    --series-name "Star Trek - Strange New Worlds" \
    --encoder nvenc --dolby-vision p81 --preserve-all-audio
```

The actual episode is encoded under `process/staging/S03D01/`. A sequential symlink is created under `Plex Movie Files/Season 3/` with the name `Star Trek - Strange New Worlds S03E01_.mkv`. Validate order before deployment.

The separate CLI allows explicit paths:

```bash
python3 -m tv.cli process \
    --input "$ROOT/rip" --staging "$ROOT/process/staging" \
    --output "$ROOT/Plex Movie Files" --series "Star Trek - Strange New Worlds" \
    --encoder nvenc --dolby-vision p81 --preserve-all-audio --dry-run
```

That CLI retains its default duration filtering (2400–5400 seconds), unlike the main CLI. Its legacy `--encode` profile parameter is still not applied by the TV pipeline; it is not an encoder-backend selector.

## Safety and acceptance

- Existing nonempty staging files are still skipped, regardless of requested backend/DV mode; a warning states that the new settings are not applied or verified. Use fresh staging for acceptance tests. There is no force-reencode option.
- Nonzero encoder results, missing/empty new output, and exceptions stop processing before the render phase. Earlier successful encodes remain staged; old Plex links are not transactionally rolled back or removed.
- Reused nonempty staging files are not validated as complete media. Back up outputs before manual cleanup.
- Confirm the actual log shows hevc_nvenc, RPU/video count matching, HDR-property verification and final Profile 8 detection. MediaInfo should identify Profile 8.1; verify copied audio/subtitle/chapter properties against the source and test playback.
- Preserve originals. Frame counts alone do not establish metadata alignment or image quality. HDR10+ is outside scope.

```bash
python3 -m unittest discover -s tests -p 'test_tv_backend.py' -v
python3 -m unittest discover -s tests -p 'test_encoder_backend.py' -v
python3 -m unittest discover -s tests -p 'test_dolby_vision.py' -v
```

Automated mocked tests do not replace the pending real-media TV NVENC/DV acceptance test.
