# ADR-030: Prep entry — import the real JD, then confirm before building

Date: 2026-09-05
Status: Accepted
Relates to: REQ-025, ADR-026 (entry ladder), ADR-028 (kit grounding)

## Context
Prep sessions built from a typed role name give generic questions ("mocho"). The
JD is what makes them specific, and we already own an importer
(`jobs.from_url.job_from_url` for links, `extract_job_from_text` for pastes) and
a one-shot scorer (`semantic_score.score_single_no_cache`). Prep is post-apply →
no tailoring, just the JD + a fit read. But scraping is fallible (wrong page,
blocked site, mis-extraction), so we must not drop the user into a session built
on the wrong posting.

## Decision
One smart input (link OR pasted JD, auto-detected). Try the DB match first
(ADR-026); on a miss, **import** + score, then show an **intermediate confirm**
(company, role, match) the user edits before creating the session. Prep stays
self-contained: the JD and score live **on the `prep_sessions` row** (new
`match_score`/`match_brief`), never by inserting into the Jobs board.

## Alternatives
- Persist scraped job into `jobs`: leaks prep-only postings into the board.
- Auto-bind, no confirm: silent wrong-JD poisons the kit.
- Keep typed company+role primary: weakest grounding — demoted to fallback.

## Consequences
Additive columns + SCHEMA bump. Entry costs a scrape + up to 2 LLM calls on a
miss (synchronous, behind an htmx busy-state) — one-time per interview. Confirm
adds a click but buys trust. Reuses the hardened importer for free.
