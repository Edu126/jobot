#!/bin/bash
# ───────────────────────────────────────────────────────────────
# Jobot — launcher for macOS. Double-click to start.
#
# By default, listens on ALL network interfaces (0.0.0.0:8000) so
# other devices on your Wi-Fi (like a partner's Mac) can reach it
# via http://<your-mac>.local:8000 — see "Share URL.command" for
# the exact link to send.
#
# Uses `caffeinate` so your Mac won't sleep while the server is up.
#
# Keep this Terminal window open while you're using Jobot.
# Close it (Cmd+Q) when you're done for the day.
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

# Discover this Mac's LAN identity so the startup banner shows the exact
# URL another device on the same Wi-Fi should hit. hostname is stable
# across IP changes (Bonjour), IP is the direct fallback.
HOSTNAME_LOCAL="$(scutil --get LocalHostName 2>/dev/null || hostname -s).local"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '')"

echo ""
echo "${BOLD}Jobot${RESET} ${DIM}— starting up…${RESET}"
echo ""
echo "  Once you see ${GREEN}\"Application startup complete\"${RESET} below,"
echo "  Jobot will be reachable at:"
echo ""
echo "    ${BOLD}http://127.0.0.1:8000${RESET}          ${DIM}(this Mac only)${RESET}"
echo "    ${BOLD}http://${HOSTNAME_LOCAL}:8000${RESET}  ${DIM}(share with anyone on your Wi-Fi)${RESET}"
[ -n "$LAN_IP" ] && echo "    ${BOLD}http://${LAN_IP}:8000${RESET}          ${DIM}(direct IP fallback)${RESET}"
echo ""
echo "  ${DIM}Keep this window open while you or anyone on your Wi-Fi is using Jobot.${RESET}"
echo "  ${DIM}Close it (Cmd+Q) when you're done for the day.${RESET}"
echo ""
echo "${DIM}────────────────────────────────────────────────${RESET}"

# Ensure the v2 stack is present (idempotent — no-op if already installed).
.venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.32' 'jinja2>=3.1' 'python-multipart>=0.0.12' 2>/dev/null || true

# Open browser on THIS Mac after 3s so uvicorn has time to bind.
(sleep 3 && open http://127.0.0.1:8000 >/dev/null 2>&1) &

# Bind to 0.0.0.0 so LAN clients can reach us. `caffeinate -s` prevents
# system sleep while the server is running — critical when the Mac is
# hosting for another person on the network. `-i` also blocks idle sleep.
exec caffeinate -i -s .venv/bin/uvicorn ui_web.main:app --host 0.0.0.0 --port 8000
