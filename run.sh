#!/bin/bash
# Jobot v2 — FastAPI + HTMX + Tailwind + DaisyUI.
# The v1 Streamlit UI is archived at _deprecated/ui_streamlit/ (see its README).
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "First-run setup: creating venv and installing deps…"
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# Idempotent: ensures the v2 stack is present even if the venv was set up under v1.
.venv/bin/pip install -q 'fastapi>=0.115' 'uvicorn[standard]>=0.32' 'jinja2>=3.1'

# Open browser once uvicorn is up (2s is enough for a warm start).
(sleep 2 && open http://127.0.0.1:8000 >/dev/null 2>&1) &

exec .venv/bin/uvicorn ui_web.main:app --host 127.0.0.1 --port 8000 --reload
