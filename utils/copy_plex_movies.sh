#!/usr/bin/env bash
#
# copy_plex_movies.sh
#
# Copies each movie's "Plex Movie Files" contents into a clean
# destination tree, organized by movie title.
#
# Usage:
#   copy_plex_movies.sh /path/to/Movies /path/to/destination
#
# Source structure expected:
#   Movies/<Title (Year)>/Plex Movie Files/{dirs and files}
#
# Result:
#   destination/<Title (Year)>/{dirs and files from Plex Movie Files}

set -euo pipefail

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

# Loop over each movie title directory
find "$src" -mindepth 1 -maxdepth 1 -type d | sort | while IFS= read -r title_dir; do
  plex_dir="$title_dir/Plex Movie Files"

  if [[ ! -d "$plex_dir" ]]; then
    echo "SKIP: No 'Plex Movie Files' in $(basename "$title_dir")"
    continue
  fi

  title=$(basename "$title_dir")
  dest_title="$dst/$title"

  echo "Copying: $title"

  # rsync the contents of Plex Movie Files into destination/<Title>/
  # The trailing slash on source copies contents, not the folder itself
    rsync -rlt "$plex_dir/" "$dest_title/"


done

echo "Done."