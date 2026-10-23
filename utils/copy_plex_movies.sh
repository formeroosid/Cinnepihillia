#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: copy_plex_movies.sh [OPTIONS] SOURCE DEST
Export a single movie/series or a collection containing 'Plex Movie Files'.
SOURCE and DEST are required; the current directory is never selected implicitly.
  -h, --help       Show this help without copying anything.
  -n, --dry-run    Preview only; no destination changes.
  --mount PATH     Require this destination filesystem to be mounted.
  --name NAME      Destination title folder (single-title source only).
Symlinks are copied as real data. Hidden entries are excluded. No deletions.
Requires Bash, GNU coreutils/findutils, util-linux, and rsync 3.2.3+.
Example:
  copy_plex_movies.sh -n --mount /mnt/mule "/path/to/Movie (Year)" /mnt/mule/Movies
HELP
}
arg_error() { printf 'Error: %s\n\n' "$*" >&2; usage >&2; exit 2; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need_value() {
  (($# >= 2)) && [[ -n "$2" && "$2" != -* ]] || arg_error "Missing value for $1"
}
(($# > 0)) || { usage; exit 2; }
dry=0; required_mount=""; name=""; positional=()
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -n|--dry-run) dry=1; shift ;;
    --mount|--name)
      need_value "$@"
      case "$1" in --mount) required_mount="$2" ;; --name) name="$2" ;; esac
      shift 2 ;;
    --) shift; positional+=("$@"); break ;;
    -*) arg_error "Unknown option: $1" ;;
    *) positional+=("$1"); shift ;;
  esac
done
((${#positional[@]} == 2)) || arg_error "SOURCE and DEST are required (exactly two paths)"
[[ -n "${positional[0]}" && -n "${positional[1]}" ]] || arg_error "SOURCE and DEST must not be empty"
set -- "${positional[@]}"
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
