# ADR-048: Competency-first prep pipeline — versioned JSON artifacts, bands not scores

Date: 2026-09-21
Status: Accepted (P1+P2 first; REQ-041). "Bands not scores" partially superseded for Practice by ADR-059 (rubric-built 0–100).
Relates to: REQ-041, ADR-047, ADR-008 (prompt conventions), GOV-005 (enhance-not-fabricate)

## Context
The pack specifies nine small Gemini calls (P1–P9), one job each, JSON out,
"never invent → null". The whole toolkit hangs off one list of **competencies**
derived from the JD (P1). P2 questions, P3 story mapping, and P4 flashcards all
consume P1's competencies, so the list must be generated once and shared, not
re-derived per call. Feedback must be **bands** (strong / solid / needs_work),
never fabricated percentages — the same honesty stance as the fit brief
(ADR-038, REQ-025).

## Decision
Build the pipeline **P1 first**: P1 (Brief) emits `competencies[]` with
per-competency resume-evidence bands; P2/P3/P4 fan out from that cached list.
Every output is stored in `prep_artifacts` keyed by a per-prompt
`PROMPT_VERSION` string (bump-to-regenerate, never delete — the ADR-008 / kit.py
convention), `temperature=0.0` for reproducibility. JSON is carried in-prompt +
`generate_json` (the established client path; no `response_schema` support yet).
Delivery metrics (WPM, filler count, seconds) are computed in **code**, never
asked of the model.

## Alternatives considered
- **One mega-prompt** (brief+questions+flashcards) — rejected: harder to debug,
  can't rerun one piece, blows the token budget, couples the caches.
- **Let each call re-derive competencies** — rejected: the lists drift and
  questions stop tracing to the brief; the credibility story breaks.

## Consequences
More round-trips per interview (mitigated: P2–P4 run in parallel after P1, and
each is cached). A schema change to any prompt is a version bump that silently
regenerates on next read. Competency IDs (`c1`…) become a join key across
artifacts we must keep stable within an interview.
