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

# ─── Privacy / secret scan ──────────────────────────────────
# Grep the zip contents for common secret patterns so we never ship
# a real API key, GitHub token, or personal .env. If ANY hit, we
# nuke the zip and abort — better a failed release than a leak.
echo ""
echo "${BOLD}Scanning zip for secrets…${RESET}"

# Patterns that indicate a real leaked value (not just the variable name).
# - AIza…              Google API keys (Gemini uses these)
# - sk-[A-Za-z0-9]{20,} OpenAI-style keys
# - ghp_/gho_/ghs_     GitHub tokens
# - xox[bp]-           Slack bot / user tokens
# - AKIA…              AWS access keys
# - =[A-Za-z0-9]{25,}  suspiciously long value after any KEY=
LEAKY='AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|ghs_[A-Za-z0-9]{30,}|xox[bp]-[A-Za-z0-9-]+|AKIA[0-9A-Z]{16}'
LEAK_HIT=$(unzip -p "$OUT" '*' 2>/dev/null | grep -aEo "$LEAKY" | head -3 || true)

if [ -n "$LEAK_HIT" ]; then
  echo "  ${RED}✗ Possible secret leaked into the zip:${RESET}"
  echo "$LEAK_HIT" | sed 's/^/    /'
  echo "  ${RED}Aborting.${RESET} Investigate + rebuild after redacting."
  rm -f "$OUT" "$LATEST"
  exit 1
fi
echo "  ${GREEN}✓${RESET} No secret patterns detected"

# Should-be-excluded paths — belt-and-suspenders in case someone edits
# the -x list incorrectly. Any of these in the zip = ship-blocker.
# Use anchored patterns so `.env.example` (safe template) isn't caught
# alongside `.env` (the real secret file).
BAD_HIT=$(unzip -Z1 "$OUT" \
  | grep -E "^${REPO_NAME}/(\.env(/|$)|data/|\.venv/|\.git/)" \
  | head -3 || true)
if [ -n "$BAD_HIT" ]; then
  echo "  ${RED}✗ Excluded paths leaked into the zip:${RESET}"
  echo "$BAD_HIT" | sed 's/^/    /'
  rm -f "$OUT" "$LATEST"
  exit 1
fi
echo "  ${GREEN}✓${RESET} No excluded paths present"

FILES_COUNT=$(unzip -l "$OUT" | tail -1 | awk '{print $2}')
echo "  ${GREEN}✓${RESET} $FILES_COUNT files inside"

echo ""
echo "${BOLD}Top-level manifest:${RESET}"
# Extract unique top-level entries under jobot-app/
unzip -Z1 "$OUT" \
  | grep -E "^${REPO_NAME}/[^/]+/?$" \
  | sort -u \
  | sed 's|^|  |'

echo ""
echo "  ${GREEN}✓${RESET} Built: ${BOLD}$OUT${RESET} ${DIM}($SIZE)${RESET}"
echo "  ${GREEN}✓${RESET} Also:  ${BOLD}$LATEST${RESET} ${DIM}(stable alias)${RESET}"
echo ""
echo "${DIM}────────────────────────────────────────${RESET}"
echo "${GREEN}${BOLD}Done. Next:${RESET}"
echo "  • Upload zip to a GitHub Release: ${DIM}gh release create v${VERSION} $OUT${RESET}"
echo "  • Or share the zip directly with the user."
echo ""
