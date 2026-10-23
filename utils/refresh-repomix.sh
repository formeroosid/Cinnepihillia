#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'HELP'
Usage: refresh-repomix.sh --source REPO_DIR [--output FILE]
Generate a Cinnephillia source bundle with repomix.
  -h, --help          Show this help without generating files.
  --source REPO_DIR   Required checkout containing Cinnephillia.py.
  --output FILE       Bundle path; default: OUTPUT_FILE or cinnephillia.md.
Relative output paths are relative to REPO_DIR. Existing output may be replaced.
REPO_DIR in the environment no longer selects a source implicitly.
Example:
  refresh-repomix.sh --source "$HOME/Cinnephiilia"
HELP
}
arg_error() { printf 'Error: %s\n\n' "$*" >&2; usage >&2; exit 2; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need_value() {
  (($# >= 2)) && [[ -n "$2" && "$2" != -* ]] || arg_error "Missing value for $1"
}
(($# > 0)) || { usage; exit 2; }
REPO_DIR=""; OUTPUT_FILE="${OUTPUT_FILE:-cinnephillia.md}"
while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --source|--output)
      need_value "$@"
      case "$1" in --source) REPO_DIR="$2" ;; --output) OUTPUT_FILE="$2" ;; esac
      shift 2 ;;
    *) arg_error "Unknown option or unexpected argument: $1" ;;
  esac
done
[[ -n "$REPO_DIR" ]] || arg_error "--source REPO_DIR is required"
HEADER_TEXT="Cinnephillia source bundle for Perplexity Space."
INCLUDE_PATTERNS="*.py,**/*.py,*.sh,**/*.sh,pyproject.toml,setup.cfg,setup.py,requirements*.txt,README*,docs/**/*.md"
IGNORE_PATTERNS=".ven/**,.venv/**,venv/**,env/**,**/__pycache__/**,**/*.pyc,**/.pytest_cache/**,**/.mypy_cache/**,**/.ruff_cache/**,tests/**,test/**,**/test_*.py,**/*_test.py,fixtures/**,samples/**,**/*.mkv,**/*.iso,**/*.png,**/*.jpg,**/*.jpeg,**/*.pdf,dist/**,build/**,*.egg-info/**,.git/**,.github/**,.idea/**,.vscode/**,cinephillia.log,cinnephillia.md,repomix.config.json*"
command -v repomix >/dev/null 2>&1 || fail "repomix not on PATH"
[[ -d "$REPO_DIR" ]] || fail "Source repository not found: $REPO_DIR"
REPO_DIR=$(realpath -e -- "$REPO_DIR")
[[ -f "$REPO_DIR/Cinnephillia.py" ]] || fail "Source is not a Cinnephillia checkout"
cd "$REPO_DIR"
printf '==> Generating %s in %s\n' "$OUTPUT_FILE" "$REPO_DIR"
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
printf '\n==> Done. Summary:\n'
ls -lh "$OUTPUT_FILE"
echo "    lines:        $(wc -l < "$OUTPUT_FILE")"
echo "    def count:    $(grep -c 'def ' "$OUTPUT_FILE" || true)"
echo "    argparse:     $(grep -c 'argparse' "$OUTPUT_FILE" || true)"
echo "    ffmpeg refs:  $(grep -c 'ffmpeg' "$OUTPUT_FILE" || true)"
printf '\n==> Coverage check:\n'
for path in movies/movie_pipeline.py Cinnephillia.py profiles utils tv/cli.py core/ffmpeg_runner.py core/ffmpeg_profiles.py; do
  if grep -qE "^## .*${path}" "$OUTPUT_FILE"; then
    echo "    OK: $path"
  else
    echo "    MISSING: $path"
  fi
done
