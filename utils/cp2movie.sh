#!/usr/bin/env bash
set -euo pipefail

# Only allow this script to run on Lumpy
if [ "$(hostname)" != "lumpy" ]; then
  echo "Error: This script may only be run on Lumpy." >&2
  exit 1
fi

DRY_RUN=0

while getopts ":n" opt; do
  case "$opt" in
    n) DRY_RUN=1 ;;
    \?)
      echo "Usage: $0 [-n]    # -n = dry run" >&2
      exit 1
      ;;
  esac
done
shift "$((OPTIND - 1))"

SRC="./"
DEST="/data/Media/Movies/"

# Require destination directory to exist
if [ ! -d "$DEST" ]; then
  echo "Error: Destination directory '$DEST' does not exist on this system." >&2
  echo "Create it first on Lumpy, then rerun this script." >&2
  exit 1
fi

RSYNC_OPTS="-avhP --owner --group --chown=jgordon:plex \
  --chmod=Du=rwx,Dg=rwx,Do=,Fu=rw,Fg=rw,Fo= \
  --exclude='.Trash*'"

if [ "$DRY_RUN" -eq 1 ]; then
  RSYNC_OPTS="$RSYNC_OPTS --dry-run --exclude='.*'"
  echo "Running in dry-run mode (no changes will be made)..."
fi

rsync $RSYNC_OPTS "$SRC" "$DEST"

if [ "$DRY_RUN" -eq 0 ]; then
  : "${PLEX_TOKEN:?PLEX_TOKEN not set}"

  PLEX_HOST="127.0.0.1"
  PLEX_PORT="32400"
  MOVIES_SECTION_ID="1"
  PLEX_TOKEN="3GTu65q1m2Dz7tecsxds"

  echo "Triggering Plex Movies metadata refresh..."
  curl -sS \
    "http://${PLEX_HOST}:${PLEX_PORT}/library/sections/${MOVIES_SECTION_ID}/refresh?force=1&X-Plex-Token=${PLEX_TOKEN}" \
    >/dev/null
fi
