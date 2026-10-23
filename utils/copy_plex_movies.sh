#!/usr/bin/env bash
# Standalone Plex export. Usage: copy_plex_movies.sh [-n] [--mount PATH] [--name NAME] SOURCE DEST
# --name overrides the title folder for a single-title source. Never deletes destination files.
set -euo pipefail
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
dry=0; required_mount=""; name=""
while (($#)); do
  case "$1" in
    -n|--dry-run) dry=1; shift ;;
    --mount|--name)
      (($# >= 2)) || fail "Missing value for $1"
      case "$1" in --mount) required_mount="$2" ;; --name) name="$2" ;; esac
      shift 2 ;;
    --) shift; break ;;
    -*) fail "Unknown option: $1" ;;
    *) break ;;
  esac
done
(($# == 2)) || fail "Usage: ${0##*/} [-n] [--mount PATH] [--name NAME] SOURCE DEST"
for tool in rsync realpath find sort mountpoint mktemp; do command -v "$tool" >/dev/null || fail "Missing tool: $tool"; done
src=$(realpath -e -- "$1"); dst=$(realpath -m -- "$2")
[[ -d "$src" ]] || fail "Source is not a directory: $src"
[[ "$dst" != "$src" && "$dst" != "$src/"* && "$src" != "$dst/"* && "$dst" != / && "$src" != / ]] || fail "Source and destination overlap"
[[ -z "$name" || ( "$name" != */* && "$name" != . && "$name" != .. ) ]] || fail "--name must be a single folder name"
if [[ -z "$required_mount" && "$dst" =~ ^(/mnt/[^/]+|/media/[^/]+)(/|$) ]]; then required_mount="${BASH_REMATCH[1]}"; fi
if [[ -n "$required_mount" ]]; then
  required_mount=$(realpath -e -- "$required_mount")
  mountpoint -q -- "$required_mount" || fail "Required filesystem is not mounted: $required_mount"
  [[ "$required_mount" == / || "$dst" == "$required_mount" || "$dst" == "$required_mount/"* ]] || fail "Destination is outside required mount"
fi
opts=(-rltL --mkpath --info=progress2 --itemize-changes '--exclude=.Trash*' '--exclude=.*')
((dry == 0)) || opts+=(--dry-run)
count=0
copy_title() {
  local title_dir="$1" title target
  [[ -d "$title_dir/Plex Movie Files" ]] || return 0
  title=${name:-${title_dir##*/}}
  target=$(realpath -m -- "$dst/$title")
  [[ "$target" == "$dst/"* ]] || fail "Title destination escapes destination tree"
  printf 'Export: %s -> %s/%s/\n' "$title_dir/Plex Movie Files" "$dst" "$title"
  if ((dry == 0)); then mkdir -p -- "$dst/$title"; fi
  rsync "${opts[@]}" -- "$title_dir/Plex Movie Files/" "$dst/$title/"
  count=$((count + 1))
}
if [[ -d "$src/Plex Movie Files" ]]; then
  copy_title "$src"
else
  [[ -z "$name" ]] || fail "--name requires a single-title source"
  listing=$(mktemp)
  trap 'rm -f -- "$listing"' EXIT
  find "$src" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z > "$listing"
  while IFS= read -r -d '' title_dir; do copy_title "$title_dir"; done < "$listing"
fi
((count > 0)) || fail "No 'Plex Movie Files' directories found"
printf 'Done: %d title(s); dry-run=%d. No destination deletions.\n' "$count" "$dry"
