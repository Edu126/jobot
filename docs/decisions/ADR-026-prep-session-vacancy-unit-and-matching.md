# ADR-026: Prep is a self-contained per-vacancy session; matching searches the tailored set and confirms

Date: 2026-09-03
Status: Accepted
Relates to: REQ-023 (Prep / land-it kit), REQ-018/ADR-021 (gap enhancement,
reused when bound), GOV-005 (enhance ≠ fabricate), ADR-019 (résumé-hash cache
key), ADR-027 (company outlook cache)

## Context

Prep's unit is the **vacancy**, created at the callback moment — which lands
*months* after apply, unpredictably (REQ-023). Constraints real now: Gemini
quota is scarce; per-user SQLite; the honesty line is non-negotiable (a wrong
vacancy binding grounds the entire kit on the wrong JD); existing artifacts
(`job_scores`, `gap_enhancements`, `tailor_runs`) key on `job_id` +
`resume_hash`; `jobs` rows are scraped provenance; the live posting URL may 404
by the time the callback arrives, so our stored copy is the reliable one.

## Decision

A new **`prep_sessions`** table, **self-contained**: it carries the vacancy's
own fields (`company`, `role_title`, `jd_text`), the candidate (`resume_hash`),
`lang`, `source` (from_job | pasted_link | pasted_text), timestamps, and an
**optional `job_id`** set only when matched. The kit stands on the session's own
fields; a `job_id` binding is *enrichment* (pulls in existing score / gaps /
defense hooks). No synthetic `jobs` row is minted for pasted vacancies.

**Creating a session IS the callback signal** — logged as a BI event; no
separate "interview" instrument.

**Matching** searches the **tailored set first** (`tailor_runs ⋈ jobs`), then
scored jobs. Ladder: exact URL → auto-bind; else company+title + JD-text
fuzzy-ratio (rapidfuzz-style, **no embeddings, no LLM**) → surface the **top 2–3
for a one-tap confirm**. Below the exact-URL bar, nothing binds silently.

## Alternatives considered

- **Mint a synthetic `jobs` row for pasted vacancies** (uniform `job_id`
  downstream): rejected for MVP — pollutes Jobs listing / gap map / search
  provenance; the kit doesn't need scoring to function. Revisit if pasted
  vacancies should flow into scoring.
- **Drive Prep off `applications.status` (interview state):** rejected —
  couples to the Journey board and the apply moment; the callback is months
  later and dropdown-find is exactly the friction we're removing.
- **Embedding similarity for matching:** rejected — infra/cost off the $0 POC;
  fuzzy string + confirm suffices.
- **Auto-bind the best fuzzy match:** rejected — a wrong bind grounds the whole
  kit on the wrong JD (honesty, GOV-005).

## Consequences

- Two enrichment paths: **bound** (reuse gaps/defense hooks by `job_id`) vs
  **unbound** (kit from session fields only). Accepted — unbound just forgoes
  reuse and still works.
- `jd_text` on the session duplicates `jobs.description` when bound; the win is
  robustness to the job row / live posting disappearing later.
- `resume_hash` freezes candidate identity like the score cache; if the résumé
  changes, the (lazy) kit re-keys on the current hash — staleness rules stay
  simple.
- Matching is heuristic; the **confirm UI is the honest backstop** *and* the
  fix for the "dropdown is hard" complaint (propose the few likely, don't make
  the user search everything).
