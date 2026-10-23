#!/usr/bin/env bash
# Standalone Lumpy deployment. Run from a collection root, or supply --source.
# Usage: cp2movie.sh [-n] [--source DIR] [--mount PATH] [--name NAME] [--no-refresh]
# --name deploys one series/movie folder under an explicit library folder name.
set -euo pipefail
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
[[ "$(hostname -s)" == lumpy ]] || fail "Run this script on Lumpy"
dry=0; source_dir=.; required_mount=""; name=""; refresh=1
while (($#)); do
  case "$1" in
    -n|--dry-run) dry=1; shift ;;
    --no-refresh) refresh=0; shift ;;
    --source|--mount|--name)
      (($# >= 2)) || fail "Missing value for $1"
      case "$1" in --source) source_dir="$2" ;; --mount) required_mount="$2" ;; --name) name="$2" ;; esac
      shift 2 ;;
    *) fail "Usage: ${0##*/} [-n] [--source DIR] [--mount PATH] [--name NAME] [--no-refresh]" ;;
  esac
done
for tool in rsync realpath find findmnt mountpoint; do command -v "$tool" >/dev/null || fail "Missing tool: $tool"; done
src=$(realpath -e -- "$source_dir")
library=$(realpath -e -- "/data/Media/Movies")
[[ -d "$src" && -d "$library" ]] || fail "Source and library directories must exist"
[[ -z "$name" || ( "$name" != */* && "$name" != . && "$name" != .. ) ]] || fail "--name must be a single folder name"
dst=$(realpath -m -- "$library${name:+/$name}")
[[ "$dst" == "$library" || "$dst" == "$library/"* ]] || fail "Destination escapes library"
[[ "$src" != / && "$dst" != "$src" && "$dst" != "$src/"* && "$src" != "$dst/"* ]] || fail "Source and destination overlap"
for marker in rip process 'Plex Movie Files'; do [[ ! -d "$src/$marker" ]] || fail "Source looks like an encode project; export its Plex files first"; done
[[ -n "$(find "$src" -type f -iname '*.mkv' -print -quit)" ]] || fail "Source contains no regular MKV files"
[[ -z "$(find "$src" -type l -iname '*.mkv' -print -quit)" ]] || fail "Export episode symlinks as real files first"
if [[ -n "$required_mount" ]]; then
  required_mount=$(realpath -e -- "$required_mount")
  mountpoint -q -- "$required_mount" || fail "Required filesystem is not mounted: $required_mount"
  [[ "$required_mount" == / || "$dst" == "$required_mount" || "$dst" == "$required_mount/"* ]] || fail "Destination is outside required mount"
else
  backing=$(findmnt -n -o TARGET --target "$library")
  [[ -n "$backing" && "$backing" != / ]] || fail "Library is on root filesystem; supply --mount / explicitly if intentional"
fi
if ((dry == 0 && refresh == 1)); then
  [[ -n "${PLEX_TOKEN:-}" ]] || fail "Set PLEX_TOKEN or use --no-refresh before copying"
  [[ "$PLEX_TOKEN" != *$'\n'* && "$PLEX_TOKEN" != *$'\r'* ]] || fail "Invalid token"
  command -v curl >/dev/null || fail "Missing tool: curl"
fi
opts=(-avhP --itemize-changes --chown=jgordon:plex --chmod=Du=rwx,Dg=rwx,Do=,Fu=rw,Fg=rw,Fo= '--exclude=.Trash*' '--exclude=.*')
((dry == 0)) || opts+=(--dry-run)
printf 'Deploy: %s/ -> %s/ (dry-run=%d)\n' "$src" "$dst" "$dry"
rsync "${opts[@]}" -- "$src/" "$dst/"
if ((dry == 0 && refresh == 1)); then
  # Token goes through stdin configuration, not the URL or process arguments.
  escaped=${PLEX_TOKEN//\\/\\\\}; escaped=${escaped//\"/\\\"}
  printf 'header = "X-Plex-Token: %s"\n' "$escaped" |
    curl --config - --fail --silent --show-error --connect-timeout 10 --max-time 60 \
      "http://127.0.0.1:32400/library/sections/1/refresh?force=1" >/dev/null
fi
printf 'Done. No destination deletions.\n'
