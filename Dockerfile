# ─────────────────────────────────────────────────────────────────────────────
# Jobot — container image for Fly.io (single-user testing deploy).
#
# Layer strategy:
#   1. Base + system deps (rarely changes → cached)
#   2. requirements.txt (changes only on dep bumps → cached across code edits)
#   3. App source (changes every deploy → invalidates only the last layer)
#
# Runtime:
#   uvicorn ui_web.main:app on 0.0.0.0:8000
#   SQLite DB persisted at /app/data (mount a Fly volume there — see fly.toml)
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Prevent Python from writing .pyc files and force stdout/stderr to flush
# immediately so `fly logs` shows output in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Minimal system deps. jobspy uses requests+bs4 (pure Python) — no chromium
# needed. curl is handy for the HEALTHCHECK and debugging via `fly ssh console`.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependency layer (cached until requirements.txt changes) ────────────────
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── App source (invalidates the layers below on every code change) ──────────
COPY . .

# Create the persistent data dir up front so a fresh boot (no volume attached
# yet, e.g. `fly ssh console` on a brand-new machine) doesn't crash. When the
# Fly volume mounts at /app/data it takes over — the mkdir is a no-op.
RUN mkdir -p /app/data

# ── Non-root user for basic hardening ───────────────────────────────────────
# UID 1000 matches Fly's default volume ownership so writes to /app/data
# from the mounted volume just work.
RUN useradd --create-home --uid 1000 --shell /bin/bash jobot \
 && chown -R jobot:jobot /app
USER jobot

EXPOSE 8000

# Fly's own health check (see fly.toml [http_service.checks]) is authoritative;
# this HEALTHCHECK is a belt-and-suspenders for `docker run` local testing.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["uvicorn", "ui_web.main:app", "--host", "0.0.0.0", "--port", "8000"]
