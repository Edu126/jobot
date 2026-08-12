# Jobot v2

Local-first job-search app. Search job boards, get AI-scored matches with
one-sentence reasoning, curate what to apply to, tailor a resume + cover
letter per posting. Single-user, runs on your laptop, $0/month.

Built for the "massive search, curated apply" philosophy — 5–10 real
applications a day, not 100 sprayed submissions.

## Run it

```bash
./run.sh
```

First run creates a venv and installs deps (a few minutes). Subsequent
runs boot instantly. The browser opens `http://127.0.0.1:8000`
automatically.

## Setup

- **Gemini API key** (free tier): [aistudio.google.com](https://aistudio.google.com).
  Put it in `jobot-app/.env`:
  ```
  GOOGLE_API_KEY=your-key-here
  ```
- **Resume**: upload a `.docx` or `.pdf` on the Profile tab. First upload
  becomes the active one.

Without a resume or API key, search still works — AI scoring and tailoring
don't. You'll see prompts in the UI when either is missing.

## What's inside

Three tabs:

- **Jobs** — pick a saved search or build a custom one; results come back
  scored by Gemini with a one-line reason per posting, matched skills, and
  gaps. Filter by score / remote / language. Click a card to save as
  interested or open the Tailor drawer.
- **Applications** — grouped by status (interested → applied → interviewing
  → offer / rejected / withdrawn). Add notes inline, move between statuses
  with a dropdown, re-tailor from here too.
- **Profile** — current resume + ATS report, upload new versions, switch
  between older uploads, API key status, saved searches.

## Architecture

```
jobot-app/
├── core/                Shared library — parsers, matching, LLM, DB
│   ├── db.py            SQLite (single file at data/jobot.db)
│   ├── jobs/            jobspy wrapper + on-disk search cache
│   ├── llm/             Gemini client, rewrite prompts, company research
│   ├── matching/        TF-IDF + Gemini semantic scoring w/ batching + cache
│   └── resume/          DOCX/PDF parser, ATS report, DOCX writer
├── ui_web/              FastAPI + Jinja + HTMX + Alpine + Tailwind + DaisyUI
│   ├── main.py          App entry + route registration
│   ├── deps.py          Shared Jinja env + filters
│   ├── state.py         Small in-memory bridge (tailored results per job)
│   ├── routes/          {jobs, applications, profile}.py
│   ├── templates/       base.html, pages/, partials/
│   └── static/          app.css (custom `jobot` DaisyUI theme)
├── data/                SQLite DB + on-disk job cache (git-ignored)
├── requirements.txt
├── run.sh               Boots FastAPI (this is v2 — primary entry)
├── PROJECT.md           Rewrite plan + phase tracker
├── smoke_semantic_score.py   TF-IDF vs Gemini comparison harness
└── _deprecated/
    └── ui_streamlit/    Archived v1 UI (see below)
```

The `core/` package is deliberately UI-agnostic — no FastAPI or Streamlit
imports leak in. That's why v2 could be built without rewriting a single
line of matching / parsing / LLM code.

## Design system

Wealthsimple-inspired minimalism:

- Custom DaisyUI theme (`jobot`) with hunter green primary, warm off-white
  base, near-black text
- Inter font (Google Fonts CDN)
- Text-only nav tabs with animated underline (no boxed tab widgets)
- Cards use borders, never shadows
- Score badges (verdict-tinted), skill chips, status pills
- Right-side drawer for Tailor flow with backdrop + Alpine transitions

Full design tokens and rules live in `ui_web/static/app.css`.

## v1 → v2 migration (what changed)

The v1 UI (Streamlit) is archived at `_deprecated/ui_streamlit/`. It works
if you `pip install streamlit` and run `streamlit run _deprecated/ui_streamlit/app.py`,
but nothing new goes there — v2 is where the work happens.

**What v2 fixed:**
- Weak TF-IDF-only scoring → **Gemini-scored** with one-sentence reasoning,
  batched 6-per-call and cached by `(resume_id, job_id)`
- "Made in Streamlit" aesthetic → clean custom UI with proper typography,
  drawer flows, quiet cards
- 6 tabs of overlapping concerns → **3 focused tabs** (Jobs / Applications /
  Profile). Tailor is a drawer, not a tab.
- Rerun-everything performance → HTMX partial swaps, Alpine for local state

**What stayed the same:**
- Same SQLite file (`data/jobot.db`) — the two UIs coexisted safely during
  the migration
- Same on-disk job-search cache
- Same DOCX/PDF parser, ATS checks, tailoring prompts
- Free-tier Gemini as the only paid dependency ($0/month)

## Troubleshooting

- **"Port 8000 already in use"** — another uvicorn is running. Kill with
  `pkill -f "uvicorn ui_web"`.
- **AI scoring doesn't run on results page** — check Profile tab; you need
  a current resume AND `GOOGLE_API_KEY` in env or `.env`.
- **Search takes 60-90 seconds** — normal. jobspy scrapes LinkedIn + Indeed
  live. Cached after; re-opening the same search is instant.
- **Alpine warnings in browser console** — Alpine loads via CDN; some
  browsers cache old versions. Hard-reload (Cmd+Shift+R).

## Companion tools

- `smoke_semantic_score.py` — run on cached search files to see TF-IDF vs
  Gemini scoring side-by-side. Useful for validating prompt changes.
- `smoke_e2e.py` — end-to-end audit of the core library (parsers,
  matching, DB). Not a test suite — a probe.
