#!/bin/bash
# ───────────────────────────────────────────────────────────────
# Update Jobot.command
#
# Applies a pending update downloaded from within the running app.
# Preserves your data, API key, and Python environment.
#
# Runs when you:
#   1. Open Jobot in your browser
#   2. Go to Profile → "Check for updates" → "Download update"
#   3. Once downloaded, close the browser tab and DOUBLE-CLICK THIS FILE
#
# What it does:
#   • Verifies dist/pending-update.zip exists
#   • Stops any running Jobot server
#   • Extracts the update over your install (skipping .venv, data, .env)
#   • Runs pip install --upgrade -r requirements.txt to catch new deps
#   • Restarts Jobot and re-opens it in your browser
# ───────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
  DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; DIM=''; BOLD=''; RESET=''
fi

echo ""
echo "${BOLD}🔄 Jobot — Update${RESET}"
echo "${DIM}────────────────────────────────────────────────${RESET}"
echo ""

# 1) Verify pending update
if [ ! -f "dist/pending-update.zip" ]; then
  echo "${YELLOW}No pending update found.${RESET}"
  echo "  First: open Jobot, go to Profile → Check for updates → Download."
  echo ""
  read -n 1 -s -r -p "Press any key to close…"
  exit 0
fi

BEFORE_VER=""
[ -f "VERSION" ] && BEFORE_VER=$(tr -d '[:space:]' < VERSION)
echo "  ${DIM}Currently installed: v${BEFORE_VER:-unknown}${RESET}"

# 2) Stop any running Jobot server (localhost only — safe)
echo ""
echo "${BOLD}1.${RESET} Stopping any running Jobot server…"
pkill -f "uvicorn ui_web.main" 2>/dev/null || true
# Give sockets a moment to release
sleep 1
echo "  ${GREEN}✓${RESET} Stopped"

# 3) Extract into a temp directory + rsync source (preserving user data)
echo ""
echo "${BOLD}2.${RESET} Applying the update…"
TMP="$(mktemp -d /tmp/jobot-update.XXXXXX)"
unzip -qq dist/pending-update.zip -d "$TMP"

# The zip contains a top-level jobot-app/ folder — find it
SRC_ROOT=""
if [ -d "$TMP/jobot-app" ]; then
  SRC_ROOT="$TMP/jobot-app"
else
  # Fallback: use the only folder inside the extracted zip
  SRC_ROOT=$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -n1)
fi

if [ -z "$SRC_ROOT" ] || [ ! -d "$SRC_ROOT" ]; then
  echo "${RED}✗ Extracted update has an unexpected structure.${RESET}"
  echo "  Restore from the last working install and re-download the release."
  rm -rf "$TMP"
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

# rsync the update over current, preserving user data + venv
rsync -a \
  --exclude=".venv/" \
  --exclude="data/" \
  --exclude=".env" \
  --exclude="dist/" \
  --exclude=".git/" \
  "$SRC_ROOT/" ./
rm -rf "$TMP"
echo "  ${GREEN}✓${RESET} Files updated"

AFTER_VER=""
[ -f "VERSION" ] && AFTER_VER=$(tr -d '[:space:]' < VERSION)

# 4) Refresh Python deps (safe even if unchanged — pip is idempotent)
echo ""
echo "${BOLD}3.${RESET} Refreshing Python dependencies (may take up to 1 min)…"
if [ -x ".venv/bin/pip" ]; then
  .venv/bin/pip install --upgrade -r requirements.txt --quiet
  echo "  ${GREEN}✓${RESET} Dependencies up to date"
else
  echo "${YELLOW}⚠ No .venv found — run 'Install Jobot.command' first, then re-run this.${RESET}"
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

# 5) Clean up the pending zip
rm -f dist/pending-update.zip

# 6) Relaunch — hand off to Start Jobot.command
echo ""
echo "${GREEN}${BOLD}✓ Update complete: v${BEFORE_VER:-?} → v${AFTER_VER:-?}${RESET}"
echo ""
echo "${DIM}Starting Jobot…${RESET}"
sleep 1

# exec replaces this shell with Start Jobot.command so the update Terminal
# window closes cleanly once Jobot is running.
exec ./"Start Jobot.command"
