# Jobot

A local-first AI job-search assistant. Search boards, get AI-scored matches, tailor your resume + cover letter for each role, and track your applications — all on your own Mac. Data never leaves your machine except for LLM calls to Google Gemini.

Built for AEC (architecture / engineering / construction) job hunters in Ottawa, but the pipeline is domain-agnostic.

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

- macOS (Windows/Linux untested but likely works — just skip the `.command` scripts and use `./run.sh`)
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

## License

MIT
