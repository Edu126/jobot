#!/bin/bash
# ───────────────────────────────────────────────────────────────
# package-release.sh
#
# Builds a portable Jobot zip a new user can extract + double-click
# to install and run. Reads version from VERSION file and stamps the
# zip filename with it. Excludes:
#   - .venv/       (user creates their own on first run)
#   - data/        (user's data starts fresh)
#   - .env         (user's own goes in there)
#   - dist/        (this script's own output — don't ship it in itself)
#   - .git/        (repo metadata not needed at runtime)
#   - PROJECT.md   (internal changelog, not for shipping)
#   - screenshots, .pyc, __pycache__, .DS_Store
#
# Output: dist/jobot-{VERSION}.zip
#         Also dist/jobot-latest.zip as a stable alias.
# ───────────────────────────────────────────────────────────────
set -e

# cd to repo root — script lives in scripts/, so go up one level
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"

if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

VERSION="dev"
if [ -f "VERSION" ]; then
  VERSION="$(tr -d '[:space:]' < VERSION)"
fi

mkdir -p dist
OUT="dist/jobot-${VERSION}.zip"
LATEST="dist/jobot-latest.zip"

echo ""
echo "${BOLD}Packaging Jobot v${VERSION}…${RESET}"
echo "${DIM}────────────────────────────────────────${RESET}"

# Sanity-check: the entry-point files that Mehran will double-click
for required in \
  "Install Jobot.command" \
  "Start Jobot.command" \
  "READ FIRST — macOS security prompt.txt" \
  "requirements.txt" \
  "run.sh"; do
  if [ ! -f "$required" ]; then
    echo "${RED}Missing required file: $required${RESET}"
    exit 1
  fi
done
echo "  ${GREEN}✓${RESET} All entry-point files present"

# Zip contents of jobot-app into a folder named jobot-app inside the zip,
# so extraction always yields a predictable `jobot-app/` folder for the user.
rm -f "$OUT" "$LATEST"

# We zip from the parent dir so the archive contains `jobot-app/` at root.
cd ..
zip -r "$REPO_ROOT/$OUT" "$REPO_NAME" \
  -x "$REPO_NAME/.venv/*" \
  -x "$REPO_NAME/data/*" \
  -x "$REPO_NAME/.env" \
  -x "$REPO_NAME/.git/*" \
  -x "$REPO_NAME/.git" \
  -x "$REPO_NAME/dist/*" \
  -x "$REPO_NAME/_deprecated/*" \
  -x "$REPO_NAME/*.pyc" \
  -x "$REPO_NAME/**/*.pyc" \
  -x "$REPO_NAME/**/__pycache__/*" \
  -x "$REPO_NAME/**/__pycache__" \
  -x "$REPO_NAME/.DS_Store" \
  -x "$REPO_NAME/**/.DS_Store" \
  -x "$REPO_NAME/PROJECT.md" \
  > /dev/null

cd "$REPO_ROOT"
cp "$OUT" "$LATEST"

SIZE=$(du -h "$OUT" | cut -f1)

echo "  ${GREEN}✓${RESET} Built: ${BOLD}$OUT${RESET} ${DIM}($SIZE)${RESET}"
echo "  ${GREEN}✓${RESET} Also:  ${BOLD}$LATEST${RESET} ${DIM}(stable alias)${RESET}"
echo ""
echo "${DIM}────────────────────────────────────────${RESET}"
echo "${GREEN}${BOLD}Done. Next:${RESET}"
echo "  • Upload zip to a GitHub Release: ${DIM}gh release create v${VERSION} $OUT${RESET}"
echo "  • Or share the zip directly with the user."
echo ""
