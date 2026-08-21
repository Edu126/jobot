# Solution Overview

Last updated: 2026-08-21

## What this is
A personal AI job-hunt agent that scrapes public job boards, scores
each posting against the user's resume with Gemini, and helps them
tailor + track applications. One deployment per user on Fly.io.

## Why it exists
LinkedIn and the job boards are optimized for recruiter engagement,
not job seeker outcomes: opaque scoring, hidden salary ranges,
sycophantic AI "coaches" that won't tell you the resume is wrong.
Jobot is small, single-user, and can afford to say the true thing.
Before jobot, the four real users were reading job boards manually,
maintaining ad-hoc resume variants, and had no view into their own
job-hunt patterns.

## Big pieces

- **`core/jobs/`** — scraping (via python-jobspy), URL import (custom
  adapters + `from_url.py` extractor), search-task background workers,
  cache. The pipeline that turns "search 3 titles" into structured
  Job rows.
- **`core/matching/semantic_score.py`** — batched Gemini scoring of
  jobs against the current resume. Returns calibrated 0–100 + verdict
  + matched/gap evidence. Cached per (resume_id, job_id).
- **`core/llm/`** — Gemini client with fallback chain, prompt
  templates for tailoring, per-identity daily cap accounting,
  kill-switch (`LLM_DISABLED`).
- **`core/resume/`** — resume parsing (deterministic + LLM re-parse
  fallback), ATS anomaly checks, contact extraction.
- **`core/bi/pulse.py`** — weekly Gemini-authored markdown report over
  the six signal tables. First-class product surface, not devops.
- **`core/db.py`** — SQLite persistence, single file per deployment,
  schema managed by idempotent DDL + monotonic version bumps.
- **`ui_web/`** — FastAPI + HTMX + Alpine + Tailwind/DaisyUI CDN.
  Renders `/jobs`, `/journey`, `/profile`, `/admin/pulse` + a floating
  settings panel and a feedback widget available from every page.

## Boundaries
What jobot deliberately does NOT do:
- No multi-tenant / shared infrastructure. See `vision.md` #1.
- No recruiter / employer surface. See `vision.md` non-goals.
- No third-party analytics or telemetry. Local pulse report only.
- No user auth (yet). The whole-app-is-per-user architecture
  substitutes for it.
- No paid tier. No monetization surface. No pricing page.
- No user-facing "Regenerate" or retry buttons. Quality lives in the
  contract layer. See `vision.md` #3.

## Constraints we're living with

- **Cost near zero.** Gemini free tier (with fallback chain of
  `gemini-3.5-flash-lite → gemini-3.1-flash-lite → gemini-2.5-flash`),
  Fly hobby plan, SQLite (no managed DB fees).
- **Solo maintainer + AI pair.** Every complexity is maintenance debt
  a single person carries.
- **4 real users**, three Fly apps: `jobbotv2` (Melissa),
  `jobbotv2-hermana` (boyfriend), `jobbotv2-melissa` (Sara — the
  historical name mismatch is preserved; renaming Fly apps would
  break bookmarks and require volume migration).
- **CGNAT reality.** Users on mobile can share IPs; identity is
  supplemented by a session cookie so rate-limit + accounting still
  work per real user.
- **Bilingual audience.** EN (default, Canada / US market) + ES
  (LatAm register — Colombia / Spain-based users all get LatAm
  Spanish, never Spain register).

## Related docs
- `docs/architecture/vision.md` — non-negotiable principles.
- `docs/architecture/components.md` — Mermaid diagram (needs
  backfill from current state).
- `docs/decisions/` — one ADR per significant decision.
