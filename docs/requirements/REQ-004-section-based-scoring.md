# REQ-004: Section-based scoring

Date: 2026-08-21
Source: User (product spec, verbatim in chat)
Status: Shipped (Sprint 7, 2026-08-26)

## What they asked for

Replace the single LLM-generated score with a weighted average across
five sections owned by the backend, not the LLM:

- Experience & Relevant Achievements (30%)
- Skills & Tools (25%)
- Role & Responsibility Alignment (20%)
- Industry / Domain Alignment (15%)
- Education & Certifications (10%)

LLM returns per-section score + matches + gaps + short reasoning.
Backend computes the final weighted score and existing verdict bands
(85+/65+/40+/<40). Hard requirements tracked separately
(Met/Partial/Missing/Unknown) and must not disappear into the average
— a score of 88 can still show a Missing hard requirement. Soft
requirements influence sections, not blockers. Location, salary,
work arrangement stay as separate signals. Persist `prompt_version`
+ `scoring_version` on `job_scores`; cache valid only when both
match current.

## What they actually need

Stabilize scoring against LLM non-determinism. A single LLM-generated
number is effectively random run-to-run; giving the model a fixed frame
(five weighted sections + backend-owned formula) forces it to reason
against a rubric instead of picking a number. The weighted average is
the anchor. Per-section reasoning is stored (useful signal, cache-worthy)
but doesn't need to surface in the UI — no card redesign required from
this REQ. Hard requirements sit outside the average so a critical
Missing item can't be silently smoothed away.

## How we'll know it worked

- Re-scoring the same (resume, job) pair yields materially stable
  section scores across runs, not the current lottery.
- A candidate with a strong overall score but a Missing hard requirement
  is still queryable as such (data preserved, even if UI stays simple).
- Bumping `prompt_version` or `scoring_version` invalidates cached
  scores logically (next read recomputes) without deleting history.

## Related

- REQ-005 (paired — removes AEC bias in the same scoring rewrite).
- ADR-006 (scoring architecture split + prompt/scoring versioning).
- ADR-007 (paired prompt debias — consumes ADR-006's versioning).
- `job_scores` table (schema change).
