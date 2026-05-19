#!/usr/bin/env bash
# refresh-repomix.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Cinnephiilia}"
OUTPUT_FILE="${OUTPUT_FILE:-cinnephillia.md}"
HEADER_TEXT="Cinnephillia source bundle for Perplexity Space."

INCLUDE_PATTERNS="*.py,**/*.py,*.sh,**/*.sh,pyproject.toml,setup.cfg,setup.py,requirements*.txt,README*,docs/**/*.md"
IGNORE_PATTERNS=".ven/**,.venv/**,venv/**,env/**,**/__pycache__/**,**/*.pyc,**/.pytest_cache/**,**/.mypy_cache/**,**/.ruff_cache/**,tests/**,test/**,**/test_*.py,**/*_test.py,fixtures/**,samples/**,**/*.mkv,**/*.iso,**/*.png,**/*.jpg,**/*.jpeg,**/*.pdf,dist/**,build/**,*.egg-info/**,.git/**,.github/**,.idea/**,.vscode/**,cinephillia.log,cinnephillia.md,repomix.config.json*"

if ! command -v repomix >/dev/null 2>&1; then
  echo "error: repomix not on PATH (try: pipx install repomix)" >&2
  exit 1
fi
[[ -d "$REPO_DIR" ]] || { echo "error: REPO_DIR not found: $REPO_DIR" >&2; exit 1; }

cd "$REPO_DIR"
echo "==> Generating $OUTPUT_FILE in $REPO_DIR"
repomix \
  -o "$OUTPUT_FILE" \
  --style markdown \
  --output-show-line-numbers \
  --remove-empty-lines \
  --no-gitignore \
  --no-security-check \
  --header-text "$HEADER_TEXT" \
  --include "$INCLUDE_PATTERNS" \
  -i "$IGNORE_PATTERNS"

echo
echo "==> Done. Summary:"
ls -lh "$OUTPUT_FILE"
echo "    lines:        $(wc -l < "$OUTPUT_FILE")"
echo "    def count:    $(grep -c 'def ' "$OUTPUT_FILE" || true)"
echo "    argparse:     $(grep -c 'argparse' "$OUTPUT_FILE" || true)"
echo "    ffmpeg refs:  $(grep -c 'ffmpeg' "$OUTPUT_FILE" || true)"

echo
echo "==> Coverage check:"
for path in movies/movie_pipeline.py Cinnephillia.py profiles utils tv/cli.py core/ffmpeg_runner.py core/ffmpeg_profiles.py; do
  if grep -qE "^## .*${path}" "$OUTPUT_FILE"; then
    echo "    ✓ $path"
  else
    echo "    ✗ $path  -- MISSING from bundle"
  fi
done
