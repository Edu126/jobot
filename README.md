# Jobot

An AI job-search assistant. Search boards, get AI-scored matches, tailor your resume + cover letter for each role, and track your applications — either locally on your Mac or on your own private Fly.io instance. Data never leaves your instance except for LLM calls to Google Gemini.

Originally built for AEC (architecture / engineering / construction) job hunters in Ottawa; the scoring pipeline is being generalized to work across any domain from the candidate's own resume context (see `docs/requirements/REQ-005-remove-aec-scoring-bias.md`).

## Quick start (macOS)

1. Download the latest release zip → extract
2. Read `READ FIRST — macOS security prompt.txt` (Gatekeeper unblock)
3. Double-click **Install Jobot.command**
4. When done, double-click **Start Jobot.command** — the app opens in your browser at `http://localhost:8000`

## What it does

- **Broad search** — scrape LinkedIn + Indeed with up to 3 queries at once, AI-score every result against your resume
- **Targeted analysis** — paste any job URL (LinkedIn, Indeed, Workday, Greenhouse, company career page) → fetch, extract, score
- **Tailor** — Conservative / Balanced / Aggressive levels rewrite your resume + cover letter to match a specific JD. Preserves history, shows score delta, exports to DOCX
- **Applications** — kanban-style tracking (interested → applied → interviewing → offer / rejected / withdrawn)
- **ATS report** — 20+ checks on your resume against ATS parsers

## Stack

- FastAPI + Jinja2 + HTMX + Alpine.js + Tailwind + DaisyUI (CDN, no build step)
- SQLite via stdlib `sqlite3`
- Google Gemini (`google-genai`) for AI scoring + tailoring
- `python-jobspy` for board scraping
- All Python; runs anywhere with Python 3.10+

## Requirements

- macOS for the local install path; Linux via the Fly.io deploy path (Docker image is Debian-based)
- Python 3.10 or newer
- A free Google Gemini API key ([get one at aistudio.google.com](https://aistudio.google.com))

## Development

```bash
git clone <your-fork> jobot
cd jobot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # then add your GOOGLE_API_KEY
./run.sh
```

Server boots at `http://127.0.0.1:8000`.

## Deploy to Fly.io

One app per user — full data isolation, own volume, own secrets, own URL. Poor-man's multi-tenancy until proper auth ships (see [`docs/decisions/ADR-001-single-tenant-per-user-fly-app.md`](docs/decisions/ADR-001-single-tenant-per-user-fly-app.md)).

```bash
brew install flyctl && fly auth signup           # one-time setup
bash scripts/deploy-fly.sh                       # deploy the base app (fly.toml)
bash scripts/deploy-fly.sh <name>                # deploy an extra per-user app: jobbotv2-<name>
KEY=<their_gemini_key> bash scripts/deploy-fly.sh <name>   # with their own Gemini key
```

Push-to-deploy is wired via `.github/workflows/deploy-fly.yml` — every push to `main` deploys all per-user apps in parallel. Add new apps to the matrix there (and in `pulse.yml` for the weekly BI report).

Full walkthrough (volumes, secrets, logs, DB access, IP-block caveats): [`docs/FLY_DEPLOY.md`](docs/FLY_DEPLOY.md).

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, research, hobby, and noncommercial-organization use. Commercial use requires a separate agreement with the author. Reading, learning from, and studying the code is fine; using it (or derivative work) as part of a paid product or commercial offering is not.
