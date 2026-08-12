#!/bin/bash
# ───────────────────────────────────────────────────────────────
# Jobot — launcher script for macOS.
# Double-click this file to start the app. It will:
#   1. Start the local server
#   2. Open Jobot in your browser
#
# Keep this Terminal window open while you're using Jobot.
# Close it (Cmd+Q) when you're done.
#
# First time? Run "Install Jobot.command" first.
# ───────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

if [ ! -d ".venv" ]; then
  echo ""
  echo "${RED}${BOLD}First-time setup not done yet.${RESET}"
  echo ""
  echo "  Please double-click ${BOLD}\"Install Jobot.command\"${RESET} first."
  echo ""
  read -n 1 -s -r -p "Press any key to close this window…"
  exit 1
fi

echo ""
echo "${BOLD}🤖 Jobot${RESET} ${DIM}— starting up…${RESET}"
echo ""
echo "  Once you see ${GREEN}\"Application startup complete\"${RESET} below,"
echo "  your browser will open automatically at:"
echo ""
echo "    ${BOLD}http://127.0.0.1:8000${RESET}"
echo ""
echo "  ${DIM}Keep this window open while you use Jobot.${RESET}"
echo "  ${DIM}Close it (Cmd+Q) when you're done for the day.${RESET}"
echo ""
echo "${DIM}────────────────────────────────────────────────${RESET}"

# Ensure the v2 stack is present (idempotent — no-op if already installed).
.venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.32' 'jinja2>=3.1' 'python-multipart>=0.0.12' 2>/dev/null || true

# Open browser after 3s so uvicorn has time to bind.
(sleep 3 && open http://127.0.0.1:8000 >/dev/null 2>&1) &

exec .venv/bin/uvicorn ui_web.main:app --host 127.0.0.1 --port 8000
