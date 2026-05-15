#!/usr/bin/env bash
#
# copy_plex_tv.sh
#
# Copies each TV series' "Plex Movie Files" contents into a clean
# destination tree, organized by series title.
#
# Usage:
#   copy_plex_tv.sh /path/to/TV_or_Series /path/to/destination
#
# Accepts either:
#   1) A TV root containing many series:
#        TV/<Series>/Plex Movie Files/...
#   2) A single series directory:
#        <Series>/Plex Movie Files/...

set -euo pipefail

PLEX_SUBDIR="Plex Movie Files"

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 SOURCE_DIR DEST_DIR" >&2
  exit 1
fi

src=$(readlink -f "$1")
dst=$(readlink -f "$2")

if [[ ! -d "$src" ]]; then
  echo "Error: Source directory does not exist: $src" >&2
  exit 1
fi

mkdir -p "$dst"

copy_one_series() {
  local series_dir="$1"
  local plex_dir="$series_dir/$PLEX_SUBDIR"

  if [[ ! -d "$plex_dir" ]]; then
    echo "SKIP: No '$PLEX_SUBDIR' in $(basename "$series_dir")"
    return 0
  fi

  local title
  title=$(basename "$series_dir")
  local dest_title="$dst/$title"

  echo "Copying: $title"
  mkdir -p "$dest_title"

  # -L follows symlinks so symlinked episode files copy as real data.
  # --info=progress2 gives a single rolling progress line per series.
  rsync -rltL --info=progress2 "$plex_dir/" "$dest_title/"
}

if [[ -d "$src/$PLEX_SUBDIR" ]]; then
  # Single-series mode.
  copy_one_series "$src"
else
  # TV-root mode: iterate immediate subdirs as series.
  found=0
  while IFS= read -r -d '' series_dir; do
    copy_one_series "$series_dir"
    found=$((found + 1))
  done < <(find "$src" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

  if [[ "$found" -eq 0 ]]; then
    echo "WARN: No series subdirectories found under: $src" >&2
  fi
fi

echo "Done."