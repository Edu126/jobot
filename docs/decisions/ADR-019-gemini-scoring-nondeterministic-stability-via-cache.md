# ADR-019: Gemini scoring isn't deterministic at temp=0 — stability via cache + honest disclaimer

Date: 2026-08-31
Status: Accepted
Relates: REQ-016, ADR-016, ADR-018 (corrects its determinism consequence), next-work.md (Mehran)

## Context
ADR-018 folded in `temperature → 0` expecting reproducible scores (Mehran's
3-different-scores). A determinism demo (`scripts/scoring_bakeoff.py
--determinism`, same résumé × JD, N runs, cache bypassed) **disproves it**: the
NEW prompt at temp=0, on the **same model** (`gemini-3.5-flash-lite`, verified —
not fallback divergence), still drifts ±3–10 points and can flip a band-edge
bucket (Mehran 85/82/88, then 88/88/85/85). OLD @ temp=0.4 was sometimes *more*
stable. Gemini is non-deterministic at temp=0; temperature isn't even the
dominant factor.

## Decision
Do **not** chase engine-level determinism (median-of-N ensemble and score
rounding weighed and rejected as cost/complexity for n=4 users). User-facing
stability comes from the **text-hash score cache** (ADR-018 / schema v17): the
first score is frozen per (resume_hash, job, lang, prompt_version) and reused,
so re-views are stable — the case Mehran actually hit. Keep `temperature=0`
(lowest variance, still the right default) but **stop claiming it guarantees
determinism**. Set expectations honestly with a **UI disclaimer** on the tailor
tab: the AI fit score is support / a highlight, not a final decision, and can
vary slightly. Responsibility stays with the user.

## Consequences
- Residual, accepted: the first-ever score varies ±~5–10, band-edge buckets can
  flip, a regenerated résumé (new text → new hash) re-rolls its score.
- Escalation if a real user complains: median-of-3 self-consistency on the first
  write (cached thereafter) — deferred, not built.
- ADR-018's "temperature → 0 for determinism" consequence is corrected here; the
  rank-then-judge engine + coverage anchoring stand.
- Disclaimer shipped bilingually (`tailor.score_disclaimer`, EN/ES).
- The `--determinism` mode stays in the bake-off as the standing check.
