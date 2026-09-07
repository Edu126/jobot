# Jobot

An AI job-search assistant. Search boards, get AI-scored matches, tailor your resume + cover letter for each role, and track your applications — either locally on your Mac or on your own private Fly.io instance. Data never leaves your instance except for LLM calls to Google Gemini.

Originally built for AEC (architecture / engineering / construction) job hunters in Ottawa, it now scores across any domain: matching is anchored to a domain-neutral persona derived from the candidate's own resume, with no hard-coded industry bias (see [`docs/decisions/ADR-013-persona-source-shared-resume-profile.md`](docs/decisions/ADR-013-persona-source-shared-resume-profile.md)).

## Quick start (macOS)

1. Download the latest release zip → extract
2. Read `READ FIRST — macOS security prompt.txt` (Gatekeeper unblock)
3. Double-click **Install Jobot.command**
4. When done, double-click **Start Jobot.command** — the app opens in your browser at `http://localhost:8000`

## What it does

- **Broad search** — scrape LinkedIn + Indeed with up to 3 queries at once, AI-score every result against your resume. Results land in a master/detail workspace: a scannable left list (compact progress-ring score + title + company) and a right pane with the full match/gap analysis
- **Targeted analysis** — paste any job URL (LinkedIn, Indeed, Workday, Greenhouse, company career page) → fetch, extract, score
- **Tailor** — Conservative / Balanced / Aggressive levels rewrite your resume + cover letter to match a specific JD. Preserves history, shows score delta, exports to DOCX
- **Journey** — the honest "how am I doing?" view: kanban pipeline (interested → applied → interviewing → offer / rejected / withdrawn), a conversion funnel, and weekly activity, in plain English
- **ATS report** — 20+ checks on your resume against ATS parsers
- **Onboarding** — first-run wizard (language pick + guided tour via Driver.js) for new users, and a "what's new" bell so returning users notice when features land

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
