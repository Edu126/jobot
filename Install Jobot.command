#!/bin/bash
# ───────────────────────────────────────────────────────────────
# Jobot — first-time setup script for macOS.
# Double-click this file. Terminal will open and walk you through:
#   1. Checking that Python 3 is installed
#   2. Creating a private virtual environment (`.venv/`)
#   3. Installing everything the app needs
#   4. Asking for your free Gemini API key and saving it privately
#
# You only need to run this ONCE. After that, use "Start Jobot.command".
# ───────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

# Nice colors — safe fallback if terminal doesn't support them
if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; DIM=''; BOLD=''; RESET=''
fi

echo ""
echo "${BOLD}🤖 Jobot — first-time setup${RESET}"
echo "${DIM}────────────────────────────────────────────────${RESET}"
echo ""

# Step 1a: Xcode Command Line Tools check (needed to actually use python3 on Mac).
# macOS ships a python3 STUB at /usr/bin/python3 that triggers the CLT installer
# popup on first real use. If we let python3 run cold, macOS pops up the CLT
# installer, but our script has already advanced past it — confusing UX. So we
# detect CLT explicitly first and hold the user's hand.
echo "${BOLD}1.${RESET} Checking for Xcode Command Line Tools…"
if ! xcode-select -p >/dev/null 2>&1; then
  echo ""
  echo "${BOLD}One-time setup needed: Xcode Command Line Tools${RESET}"
  echo ""
  echo "  Python 3 on Mac needs these — they're free and Apple-provided."
  echo "  I'll trigger the installer popup now."
  echo ""
  # Fire the installer popup asynchronously
  xcode-select --install 2>/dev/null || true
  sleep 1
  echo "${BOLD}What happens next:${RESET}"
  echo ""
  echo "  1. A popup appears from macOS: ${DIM}'The xcode-select command requires...'${RESET}"
  echo "  2. Click ${BOLD}Install${RESET} (not Get Xcode — you don't need full Xcode)."
  echo "  3. Accept the license."
  echo "  4. Wait 5-10 minutes for it to download + install (~500 MB)."
  echo "  5. When done, ${BOLD}double-click 'Install Jobot.command' AGAIN${RESET}"
  echo "     to continue this setup — it'll pick up from where it left off."
  echo ""
  echo "${DIM}(This is a one-time thing. Every macOS Python user needs this.)${RESET}"
  echo ""
  read -n 1 -s -r -p "Press any key to close this window…"
  exit 0
fi
CLT_PATH=$(xcode-select -p)
echo "  ${GREEN}✓${RESET} Command Line Tools present: ${DIM}$CLT_PATH${RESET}"

# Step 1b: Python itself — and specifically Python 3.10+
# (python-jobspy and google-genai both require >=3.10; macOS-shipped stub
#  is typically 3.9, which fails at pip install time with a confusing error.)
echo ""
echo "${BOLD}2.${RESET} Checking for Python 3.10 or newer…"
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "${RED}✗ Python 3 not found even though Command Line Tools are installed.${RESET}"
  echo "  Install Python from ${BOLD}https://www.python.org/downloads/${RESET}"
  echo "  (Get the latest 3.x installer for macOS — click the .pkg to install.)"
  echo ""
  read -n 1 -s -r -p "Press any key to close this window…"
  exit 1
fi
PY_VERSION=$(python3 --version 2>&1)
# Extract MAJOR.MINOR and compare numerically
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info[0])' 2>/dev/null || echo 0)
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 0)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
  echo ""
  echo "${RED}✗ Your Python is too old: $PY_VERSION${RESET}"
  echo "  Jobot needs ${BOLD}Python 3.10 or newer${RESET}."
  echo ""
  echo "${BOLD}How to fix (5 minutes):${RESET}"
  echo ""
  echo "  1. Go to ${BOLD}https://www.python.org/downloads/${RESET}"
  echo "  2. Click the yellow ${BOLD}\"Download Python 3.x.x\"${RESET} button"
  echo "     ${DIM}(any 3.x that starts with 3.10, 3.11, 3.12, or 3.13 is perfect)${RESET}"
  echo "  3. Open the downloaded ${BOLD}.pkg${RESET} file and click through the installer"
  echo "  4. Come back here and ${BOLD}double-click 'Install Jobot.command' AGAIN${RESET}"
  echo ""
  echo "${DIM}(python.org's installer is the official one from the Python team —${RESET}"
  echo "${DIM} it's safe and takes ~2 min. No Homebrew required.)${RESET}"
  echo ""
  read -n 1 -s -r -p "Press any key to close this window…"
  exit 1
fi
echo "  ${GREEN}✓${RESET} Found: $PY_VERSION"

# Step 3: Virtual env
echo ""
echo "${BOLD}3.${RESET} Setting up a private Python environment…"
if [ -d ".venv" ]; then
  echo "  ${DIM}(already exists — will reuse)${RESET}"
else
  python3 -m venv .venv
  echo "  ${GREEN}✓${RESET} Created ${DIM}.venv/${RESET}"
fi

# Step 4: Install deps
echo ""
echo "${BOLD}4.${RESET} Installing dependencies… (this can take 2-3 minutes the first time)"
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -q -r requirements.txt
.venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.32' 'jinja2>=3.1' 'python-multipart>=0.0.12'
echo "  ${GREEN}✓${RESET} All packages installed"

# Step 5: API key
echo ""
echo "${BOLD}5.${RESET} Gemini API key"
echo ""
if [ -f ".env" ] && grep -q "GOOGLE_API_KEY=..[^\"']" .env 2>/dev/null; then
  echo "  ${GREEN}✓${RESET} An API key is already saved in ${DIM}.env${RESET}"
  echo "  ${DIM}(to change it later, edit .env or use the Profile tab in the app)${RESET}"
else
  echo "  You need a free Gemini API key to use the AI features."
  echo "  Get one at: ${BOLD}https://aistudio.google.com${RESET}"
  echo "    (sign in with any Google account → 'Create API key' → copy)"
  echo ""
  echo "  ${DIM}Your key stays private — it's saved only on this Mac, never shared.${RESET}"
  echo ""
  read -p "  Paste your API key here (or press Enter to skip): " API_KEY
  if [ -n "$API_KEY" ]; then
    # Preserve any other env vars in .env
    if [ -f ".env" ]; then
      grep -v "^GOOGLE_API_KEY=" .env > .env.tmp 2>/dev/null || true
      mv .env.tmp .env
    fi
    echo "GOOGLE_API_KEY=$API_KEY" >> .env
    chmod 600 .env
    echo "  ${GREEN}✓${RESET} Saved to ${DIM}.env${RESET}"
  else
    echo "  ${DIM}Skipped — you can add it later from the Profile tab.${RESET}"
  fi
fi

# Step 6: Clear macOS quarantine on the folder so Start Jobot.command
# can be double-clicked without another "Apple could not verify" prompt.
# Safe to fail silently — worst case Mehran uses right-click → Open again.
echo ""
echo "${BOLD}6.${RESET} Clearing macOS quarantine flag on installed files…"
xattr -dr com.apple.quarantine . 2>/dev/null || true
echo "  ${GREEN}✓${RESET} Done"

# Done
echo ""
echo "${DIM}────────────────────────────────────────────────${RESET}"
echo "${GREEN}${BOLD}✓ Setup complete!${RESET}"
echo ""
echo "  Now double-click ${BOLD}\"Start Jobot.command\"${RESET} to launch the app."
echo "  ${DIM}(no more Apple security prompts after this — I just cleared them.)${RESET}"
echo ""
read -n 1 -s -r -p "Press any key to close this window…"
echo ""
