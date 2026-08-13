#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy-fly.sh — one-shot Fly.io deploy for Jobot v0.5-dev (testing).
#
# Usage:
#   bash scripts/deploy-fly.sh                # deploy the app in fly.toml
#   bash scripts/deploy-fly.sh melissa        # deploy 'jobbotv2-melissa'  (separate app+volume+URL)
#   bash scripts/deploy-fly.sh hermana        # deploy 'jobbotv2-hermana'
#   APP=my-custom bash scripts/deploy-fly.sh  # override app name completely
#   KEY=<gemini_key> bash scripts/deploy-fly.sh melissa   # set THAT user's key at deploy time
#
# One-user-per-app is our poor-man's multi-tenancy while proper auth
# (magic-link + user-scoped DB) is on the roadmap. Each app gets its
# own machine + volume + URL — full data isolation, zero shared state,
# stays free on Fly's 3-app allowance.
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

# API key priority: env var override → .env file. First lets you deploy
# a per-user app with THEIR key without touching your own .env.
if [ -n "${KEY:-}" ]; then
  GOOGLE_API_KEY="$KEY"
  ok "Using API key from KEY env var (${#GOOGLE_API_KEY} chars)"
else
  GOOGLE_API_KEY="$(grep -E '^GOOGLE_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')"
  if [ -z "$GOOGLE_API_KEY" ]; then
    fail "GOOGLE_API_KEY is empty in .env — fill it in first, or pass KEY=<key> when running."
  fi
  ok "Found GOOGLE_API_KEY in .env (${#GOOGLE_API_KEY} chars)"
fi

# ── 2. Resolve app name ─────────────────────────────────────────────────────
# Priority: APP env var → CLI arg → fly.toml. When CLI arg is a short suffix
# (e.g. "melissa"), the base app name from fly.toml gets suffixed:
#   'jobbotv2' + 'melissa' → 'jobbotv2-melissa'
# When APP is set directly, that's the full name (no suffixing).
BASE_APP="$(grep -E '^app[[:space:]]*=' fly.toml | head -1 \
  | sed -E "s/.*=[[:space:]]*['\"]([^'\"]+)['\"].*/\1/")"
if [ -z "$BASE_APP" ] || [ "$BASE_APP" = "$(grep -E '^app[[:space:]]*=' fly.toml | head -1)" ]; then
  fail "Couldn't parse app name from fly.toml"
fi

if [ -n "${APP:-}" ]; then
  APP_NAME="$APP"
elif [ -n "${1:-}" ]; then
  APP_NAME="${BASE_APP}-${1}"
else
  APP_NAME="$BASE_APP"
fi

# Fly requires lowercase letters, digits, dashes only.
if ! echo "$APP_NAME" | grep -qE '^[a-z0-9-]+$'; then
  fail "App name '$APP_NAME' must be lowercase letters, digits, and dashes only."
fi
info "App name: ${BOLD}${APP_NAME}${RESET}"

# ── 3. Register app if not present ──────────────────────────────────────────
if ! fly status --app "$APP_NAME" >/dev/null 2>&1; then
  warn "App '${APP_NAME}' not registered on your Fly account yet."
  info "Running: fly apps create ${APP_NAME}"
  fly apps create "$APP_NAME" || \
    fail "fly apps create failed. If the name was taken globally, pick another with APP=<name>."
  ok "App registered."
else
  ok "App '${APP_NAME}' already registered."
fi

# ── 4. Volume (idempotent) ──────────────────────────────────────────────────
if fly volumes list --app "$APP_NAME" 2>/dev/null | grep -q "jobot_data"; then
  ok "Volume 'jobot_data' already exists — skipping create."
else
  info "Creating 1GB volume 'jobot_data' in yyz…"
  fly volumes create jobot_data --size 1 --region yyz --app "$APP_NAME" --yes
  ok "Volume created."
fi

# ── 5. Secrets ──────────────────────────────────────────────────────────────
info "Setting GOOGLE_API_KEY secret…"
fly secrets set "GOOGLE_API_KEY=${GOOGLE_API_KEY}" --app "$APP_NAME" --stage
ok "Secret staged (will apply on next deploy)."

# ── 6. Deploy ───────────────────────────────────────────────────────────────
echo ""
info "Building + deploying (this takes 2-4 min the first time)…"
# --config fly.toml + --app override lets us reuse the same config file for
# multiple apps. Fly uses the app name from --app, not from fly.toml.
fly deploy --config fly.toml --app "$APP_NAME"

# ── 6. Print URL ────────────────────────────────────────────────────────────
echo ""
echo "${GREEN}${BOLD}Deployed.${RESET}"
echo ""
echo "  URL:      ${BOLD}https://${APP_NAME}.fly.dev${RESET}"
echo "  Logs:     fly logs --app ${APP_NAME}"
echo "  SSH:      fly ssh console --app ${APP_NAME}"
echo "  Status:   fly status --app ${APP_NAME}"
echo ""
