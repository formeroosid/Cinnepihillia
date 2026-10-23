#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: cp2tv.sh [OPTIONS]
Deploy exported media on Lumpy into /data/Media/TV Shows/.
Run with no arguments for this help. With any option, the source
defaults to the current directory unless --source DIR is given.
  -h, --help       Show this help on any host without copying anything.
  --source DIR     Collection root, or one title with --name.
                   Default: current directory (when other options given).
  -n, --dry-run    Preview only; no copy or Plex refresh; no token needed.
  --mount PATH     Require this destination filesystem to be mounted.
  --name NAME      Explicit library folder for a single-title source.
  --no-refresh     Copy without requesting a Plex refresh.
An implicit source is refused if it is /, $HOME, or a mount root
(e.g. /mnt/mule); pass --source explicitly to override. Any source
containing this script is refused. Hidden entries are excluded.
Live refresh requires PLEX_TOKEN in the environment.
Existing differing files may be replaced. No backups or deletions.
Examples (cd into the source first):
  cp2tv.sh -n                        Preview the current directory
  cp2tv.sh -n --name "${PWD##*/}"    Preview one title into its folder
  cp2tv.sh --source .                Copy current directory, refresh Plex
HELP
}
arg_error() { printf 'Error: %s\n\n' "$*" >&2; usage >&2; exit 2; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need_value() {
  (($# >= 2)) && [[ -n "$2" && "$2" != -* ]] || arg_error "Missing value for $1"
}
(($# > 0)) || { usage; exit 2; }
dry=0; source_dir=""; required_mount=""; name=""; refresh=1
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -n|--dry-run) dry=1; shift ;;
    --no-refresh) refresh=0; shift ;;
    --source|--mount|--name)
      need_value "$@"
      case "$1" in --source) source_dir="$2" ;; --mount) required_mount="$2" ;; --name) name="$2" ;; esac
      shift 2 ;;
    *) arg_error "Unknown option or unexpected argument: $1" ;;
  esac
done
[[ -z "$name" || ( "$name" != */* && "$name" != . && "$name" != .. ) ]] || arg_error "--name must be a single folder name"
implicit=0
if [[ -z "$source_dir" ]]; then implicit=1; source_dir=$PWD; fi
[[ "$(hostname -s)" == lumpy ]] || fail "Run this script on Lumpy"
for tool in rsync realpath find findmnt mountpoint; do command -v "$tool" >/dev/null || fail "Missing tool: $tool"; done
src=$(realpath -e -- "$source_dir") || fail "Source not found: $source_dir"
[[ -d "$src" ]] || fail "Source is not a directory: $src"
[[ "$src" != / ]] || fail "Refusing / as source"
self=$(realpath -e -- "${BASH_SOURCE[0]}")
[[ "$self" != "$src/"* ]] || fail "Source $src contains this script; cd into the TV or Movies folder first"
if ((implicit)); then
  home=$(realpath -m -- "${HOME:-/nonexistent}")
  [[ "$src" != "$home" ]] || fail "Refusing home directory as implicit source; cd elsewhere or use --source"
  ! mountpoint -q -- "$src" || fail "Refusing mount root $src as implicit source; cd lower or use --source $src"
fi
library=$(realpath -e -- "/data/Media/TV Shows") || fail "Library directory not found: /data/Media/TV Shows"
[[ -d "$library" ]] || fail "Library is not a directory: $library"
dst=$(realpath -m -- "$library${name:+/$name}")
[[ "$dst" == "$library" || "$dst" == "$library/"* ]] || fail "Destination escapes library"
[[ "$dst" != "$src" && "$dst" != "$src/"* && "$src" != "$dst/"* ]] || fail "Source and destination overlap"
for marker in rip process 'Plex Movie Files'; do [[ ! -d "$src/$marker" ]] || fail "Source looks like an encode project; export its Plex files first"; done
[[ -n "$(find "$src" -type f -iname '*.mkv' -print -quit)" ]] || fail "Source contains no regular MKV files: $src"
[[ -z "$(find "$src" -type l -iname '*.mkv' -print -quit)" ]] || fail "Export episode symlinks as real files first"
if [[ -n "$required_mount" ]]; then
  required_mount=$(realpath -e -- "$required_mount") || fail "Required mount path not found"
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
opts=(-avhP --itemize-changes --chown=jgordon:plex '--chmod=Du=rwx,Dg=rwx,Do=,Fu=rw,Fg=rw,Fo=' '--exclude=.Trash*' '--exclude=.*')
((dry == 0)) || opts+=(--dry-run)
label=explicit; ((implicit == 0)) || label="current directory"
printf 'Source (%s): %s/\nDest: %s/\ndry-run=%d refresh=%d\n' "$label" "$src" "$dst" "$dry" "$refresh"
rsync "${opts[@]}" -- "$src/" "$dst/"
if ((dry == 0 && refresh == 1)); then
  # Token goes through stdin configuration, not the URL or process arguments.
  escaped=${PLEX_TOKEN//\\/\\\\}; escaped=${escaped//\"/\\\"}
  printf 'header = "X-Plex-Token: %s"\n' "$escaped" |
    curl --config - --fail --silent --show-error --connect-timeout 10 --max-time 60 \
      "http://127.0.0.1:32400/library/sections/2/refresh?force=1" >/dev/null
fi
printf 'Done. No destination deletions.\n'
