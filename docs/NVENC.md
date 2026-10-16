# NVIDIA / NVENC movie encoding

This guide describes the opt-in backend on `feat/nvenc-backend` (PR #10). Native remains the default. The branch is not yet accepted for merge; see the checklist below.

## Scope

- Supported entry point: `Cinnephillia.py --type movie --encoder nvenc`.
- Applies to features and extras selected by `--mode`.
- Uses NVIDIA HEVC encoding on GPU 0; there is no GPU-selection CLI option.
- Does not enable GPU decoding.
- TV NVENC is rejected, not silently ignored.
- There is no automatic fallback to software encoding when NVENC fails.
- Audio, selected subtitle, and chapters use the shared runner; NVENC changes video encoding only.

## Prerequisites and checks

Use the intended execution environment, including the container if applicable:

```bash
command -v python3 ffmpeg ffprobe
nvidia-smi
ffmpeg -hide_banner -encoders | grep -w hevc_nvenc
ffmpeg -hide_banner -h encoder=hevc_nvenc

# Also required when preserving Dolby Vision
command -v dovi_tool mkvmerge
```

A listed encoder is not proof that the GPU/driver is usable. Confirm that the selected GPU supports the required HEVC mode; UHD uses Main10. Real runs perform a one-frame encoder preflight with the profile arguments; dry runs skip it. If it fails, inspect the logged ffmpeg command and driver/runtime error before starting a long encode. No VAAPI device is needed for the NVENC profiles themselves.

## Settings

Common arguments: `-c:v hevc_nvenc -gpu 0 -preset p6 -tune hq -rc vbr -b:v 0 -fps_mode passthrough`.

| Profile | Format filter | HEVC profile | CQ | Color options |
|---|---|---|---|---|
| `4k` | `format=p010le` | main10 | 23 | tv range, bt2020 primaries, smpte2084 transfer, bt2020nc matrix |
| `bluray` | `format=nv12` | main | 20 | bt709 primaries/transfer/matrix |
| `sd` | `format=nv12` | main | 20 | No explicit color override |

These are fixed starting settings in `core/ffmpeg_profiles.py`, not CLI quality controls. CQ is not numerically interchangeable with x265 CRF; compare output quality and size before adopting it for a library.

Feature profiles are selected by resolution. UHD selection forces the listed BT.2020/PQ options, so do not treat it as automatic HDR detection or SDR-to-HDR conversion. Unknown dimensions fall back to the HD profile. Movie extras always select the HD profile regardless of source size; there is no automatic 720p scale despite the legacy `extras_720p` label. UHD extras therefore do not receive the UHD/Dolby Vision treatment.

## Safe first run

Prepare an isolated movie root with a `rip/` directory containing the intended source MKV. Do not use an output directory containing a valuable existing encode: the shared ffmpeg command uses `-y`. The CLI has no short-sample option, so a real run processes the full supplied source.

```bash
# Start from the repository root
python3 Cinnephillia.py "/path/to/isolated/Movie Title (YYYY)" \
    --type movie --mode feature --encoder nvenc \
    --preserve-all-audio --dolby-vision p81 --dry-run
```

For an applicable UHD Dolby Vision source, `p81` requires source DV metadata plus both external tools. For a non-DV test, use `--dolby-vision off`. `auto` is appropriate when fallback without Dolby Vision is acceptable. Forced DV modes only apply when the selected profile is `4k`.

Check the log for:

1. Correct source and isolated output paths.
2. Expected profile name and `hevc_nvenc` settings.
3. All desired audio mappings, selected subtitle, and chapter mapping.
4. The intended Dolby Vision plan.

Dry runs still perform source probes and may create directories. They do not validate hardware, output metadata, or playback. Check free space on the output filesystem, then remove only `--dry-run` when ready.

```bash
df -h "/path/to/isolated/Movie Title (YYYY)"
```

For features and extras together, use `--mode both`. For native encoding, omit `--encoder nvenc` or explicitly use `--encoder native`. This backend switch does not undo or restore already written files.

## Dolby Vision and HDR preservation

The UHD path extracts/converts the RPU, encodes the base video, compares RPU frames with encoded video packets, injects the RPU, and remuxes to Matroska. Structured ffprobe JSON avoids the earlier CSV parsing problem for video counts/frame rate.

Before raw-HEVC extraction/remux, the helper reads available color range, matrix, transfer, primaries, mastering chromaticities/white point, luminance, MaxCLL, and MaxFALL from the encoded MKV using `mkvmerge -J`. It applies discovered properties to the replacement video track and checks them afterward. Missing properties are not invented.

Important limits:

- The donor is the encoded MKV, not the original rip. If metadata was already lost during encoding, this remux fix cannot restore it.
- This preserves Matroska container properties; it does not add static HDR SEI messages to elementary HEVC.
- Profile 7 enhancement-layer preservation is unsupported. `p76` currently warns and uses Profile 8.1 conversion.
- Automated output verification requires detected Profile 8 but does not explicitly check compatibility ID 1. Verify Profile 8.1 separately during acceptance.
- Metadata reports do not establish playback compatibility or image quality.

A handled Dolby Vision post-processing failure removes the final output and retains `.cinne-dv-*` containing `encode_hdr10.mkv` and `rpu.bin` for inspection. Preserve those artifacts and the log before retrying. RPU extraction or base encoding failures follow different cleanup paths. Allow space for the encoded MKV, temporary HEVC streams, and remuxed output.

## Acceptance checklist

Run from an updated, clean feature-branch checkout. Back up/reconcile local parser overlays or unrelated work before updating; do not reset a dirty worktree blindly.

```bash
git status --short
git branch --show-current
git log -3 --oneline
python3 -m unittest discover -s tests -p 'test_dolby_vision.py' -v
python3 -m unittest discover -s tests -p 'test_encoder_backend.py' -v
```

- [ ] Unit tests pass against the committed files.
- [ ] A short, independently prepared DV test source runs through the committed CLI and automated remux fix without manual metadata repair.
- [ ] Logs show matching RPU/video counts, Profile 8 verification, and copied HDR-property verification.
- [ ] Final DV configuration confirms Profile 8.1 / compatibility ID 1.
- [ ] Source, encoded intermediate (when retained), and final output have the expected HDR/color properties; distinguish container fields from HEVC SEI.
- [ ] Audio track counts, order, codecs, titles/languages, selected subtitle, and chapter names/times are checked.
- [ ] Target-player playback and image quality are accepted.
- [ ] HD, SD, named extras, and unmatched extras receive real-media testing.
- [ ] Native defaults remain unchanged and TV rejects `--encoder nvenc`.

Optional inspection commands (MediaInfo must be installed separately):

```bash
mediainfo "/path/to/output.mkv"
ffprobe -v error -show_streams -show_chapters -of json "/path/to/output.mkv"
mkvmerge -J "/path/to/output.mkv"
```

### Evidence so far

Earlier tests on Larry demonstrated Main10 NVENC and a 723-frame DV sample. A full-length Chinatown run completed encoding/injection with the local parser overlay, but lost HDR container fields during remux. A manual non-reencoding repair restored the reported fields. The branch now includes the JSON parser and automated container-preservation fix plus unit tests. That manual repair is not evidence that the committed automated fix has passed hardware regression. Keep PR #10 unmerged until that regression and review are complete.
