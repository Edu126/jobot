#!/bin/bash
# ───────────────────────────────────────────────────────────────
# Share URL.command
#
# Prints the URLs another device on your Wi-Fi can use to reach the
# Jobot server running on THIS Mac. Double-click to see them, copy
# one, and send it to whoever's borrowing your host.
#
# Bonjour hostname (foo.local) is preferred — it survives IP changes.
# The raw IP is the fallback if the other device's OS can't resolve
# .local names (rare on modern Macs / iPhones, common on some routers).
# ───────────────────────────────────────────────────────────────
set -e

if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; DIM=''; BOLD=''; RESET=''
fi

HOSTNAME_LOCAL="$(scutil --get LocalHostName 2>/dev/null || hostname -s).local"
# Try both common interfaces — en0 is Wi-Fi on most modern Macs, en1
# on older or Ethernet-adapter setups.
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '')"

# Detect whether the Jobot server is actually running so the URLs mean
# something. `nc -z` returns 0 when the port is open.
if nc -z 127.0.0.1 8000 2>/dev/null; then
  STATE="${GREEN}running${RESET}"
else
  STATE="${DIM}not running (double-click 'Start Jobot.command' first)${RESET}"
fi

echo ""
echo "${BOLD}Share Jobot on your Wi-Fi${RESET}"
echo "${DIM}────────────────────────────────────────${RESET}"
echo ""
echo "  Server status: $STATE"
echo ""
echo "  ${BOLD}Send either link to Mehran${RESET} — both work while your"
echo "  Mac is on the same Wi-Fi:"
echo ""
echo "    ${BOLD}http://${HOSTNAME_LOCAL}:8000${RESET}"
echo "    ${DIM}↑ recommended — this URL survives Wi-Fi disconnects / IP changes${RESET}"
echo ""
if [ -n "$LAN_IP" ]; then
  echo "    ${BOLD}http://${LAN_IP}:8000${RESET}"
  echo "    ${DIM}↑ fallback — raw IP; only reliable while your router keeps this address${RESET}"
  echo ""
fi
echo "${DIM}────────────────────────────────────────${RESET}"
echo ""
echo "  Copy the top URL to clipboard? [y/N]"
read -n 1 -s -r choice
echo ""
if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
  printf "http://${HOSTNAME_LOCAL}:8000" | pbcopy
  echo "  ${GREEN}✓${RESET} Copied. Now paste into iMessage / AirDrop / wherever."
  echo ""
fi

echo "  ${DIM}If Mehran's browser says 'can't connect':${RESET}"
echo "    1. Is your Jobot Terminal window still open? (server must be running)"
echo "    2. Is his device on the same Wi-Fi as yours?"
echo "    3. Try the raw IP link above."
echo "    4. Check macOS firewall: System Settings → Network → Firewall → Options"
echo "       → make sure Python is allowed incoming connections."
echo ""
read -n 1 -s -r -p "Press any key to close this window…"
echo ""
