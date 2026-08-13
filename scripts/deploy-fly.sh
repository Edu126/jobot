#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy-fly.sh — one-shot Fly.io deploy for Jobot v0.5-dev (testing).
#
# Usage:
#   bash scripts/deploy-fly.sh
#
# What it does (in order):
#   1. Preflight — check `fly` CLI is installed and you're logged in
#   2. First-run — if no fly.toml is registered yet, do `fly launch --no-deploy`
#   3. Create the SQLite volume (idempotent — skips if it already exists)
#   4. Push GOOGLE_API_KEY from local .env into Fly secrets
#   5. Deploy the image
#   6. Print the URL
#
# See docs/FLY_DEPLOY.md for the human walkthrough.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# cd to repo root (script lives in scripts/)
cd "$(dirname "$0")/.."

if [ -t 1 ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
  DIM=$'\033[2m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; DIM=''; BOLD=''; RESET=''
fi

info()  { echo "${DIM}→${RESET} $*"; }
ok()    { echo "${GREEN}✓${RESET} $*"; }
warn()  { echo "${YELLOW}!${RESET} $*"; }
fail()  { echo "${RED}✗${RESET} $*" >&2; exit 1; }

# ── 1. Preflight ────────────────────────────────────────────────────────────
echo ""
echo "${BOLD}Jobot → Fly.io deploy${RESET}"
echo "${DIM}────────────────────────────────────────${RESET}"

if ! command -v fly >/dev/null 2>&1; then
  fail "The \`fly\` CLI isn't installed.
    Install it:   brew install flyctl
    Then log in:  fly auth signup   (or)   fly auth login"
fi
ok "fly CLI found: $(fly version | head -1)"

# `fly auth whoami` exits non-zero when not logged in.
if ! fly auth whoami >/dev/null 2>&1; then
  fail "You're not logged in to Fly.io.
    Sign up:  fly auth signup
    Log in:   fly auth login
    Then re-run this script."
fi
ok "Logged in as: $(fly auth whoami)"

if [ ! -f ".env" ]; then
  fail "No .env at repo root. Create one from .env.example and add GOOGLE_API_KEY."
fi

GOOGLE_API_KEY="$(grep -E '^GOOGLE_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
if [ -z "$GOOGLE_API_KEY" ]; then
  fail "GOOGLE_API_KEY is empty in .env — fill it in first."
fi
ok "Found GOOGLE_API_KEY in .env (${#GOOGLE_API_KEY} chars)"

# ── 2. First-run: register the app if fly.toml's app name isn't claimed yet ─
APP_NAME="$(grep -E '^app\s*=' fly.toml | head -1 | cut -d'"' -f2)"
if [ -z "$APP_NAME" ]; then
  fail "Couldn't read app name from fly.toml"
fi
info "App name: ${BOLD}${APP_NAME}${RESET}"

if ! fly status --app "$APP_NAME" >/dev/null 2>&1; then
  warn "App '${APP_NAME}' not registered on your Fly account yet."
  info "Running: fly launch --copy-config --no-deploy --name ${APP_NAME}"
  echo "${DIM}(If the name is taken, Fly will prompt you for a different one — "
  echo "then update the \`app = \"...\"\` line in fly.toml to match.)${RESET}"
  fly launch --copy-config --no-deploy --name "$APP_NAME" --region iad || \
    fail "fly launch failed. If the name was taken, edit fly.toml and re-run."
  ok "App registered."
else
  ok "App '${APP_NAME}' already registered."
fi

# ── 3. Volume (idempotent) ──────────────────────────────────────────────────
if fly volumes list --app "$APP_NAME" 2>/dev/null | grep -q "jobot_data"; then
  ok "Volume 'jobot_data' already exists — skipping create."
else
  info "Creating 1GB volume 'jobot_data' in iad…"
  fly volumes create jobot_data --size 1 --region iad --app "$APP_NAME" --yes
  ok "Volume created."
fi

# ── 4. Secrets ──────────────────────────────────────────────────────────────
info "Setting GOOGLE_API_KEY secret…"
fly secrets set "GOOGLE_API_KEY=${GOOGLE_API_KEY}" --app "$APP_NAME" --stage
ok "Secret staged (will apply on next deploy)."

# ── 5. Deploy ───────────────────────────────────────────────────────────────
echo ""
info "Building + deploying (this takes 2-4 min the first time)…"
fly deploy --app "$APP_NAME"

# ── 6. Print URL ────────────────────────────────────────────────────────────
echo ""
echo "${GREEN}${BOLD}Deployed.${RESET}"
echo ""
echo "  URL:      ${BOLD}https://${APP_NAME}.fly.dev${RESET}"
echo "  Logs:     fly logs --app ${APP_NAME}"
echo "  SSH:      fly ssh console --app ${APP_NAME}"
echo "  Status:   fly status --app ${APP_NAME}"
echo ""
