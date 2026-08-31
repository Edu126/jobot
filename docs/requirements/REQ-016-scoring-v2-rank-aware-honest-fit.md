# REQ-016: Scoring v2 — rank-aware, honest, trusted fit

Date: 2026-08-27
Source: Eduardo (product architect) + RESEARCH-market-thesis (iteration 2)
Status: Backlog — not started

## What they asked for

A fit score the user *trusts* and that reflects how the real gate works.
After ADR-015 reverted to a single LLM value, the research on how modern
ATS rank resumes (RESEARCH-market-thesis, iteration 2) reframes the target:
recruiters read an **AI-scored, ranked list top-down**. So the score must be
rank-aware, honest, and non-gameable — answering the real user question
("is this valid? how do I move it?").

## What they actually need

- **Rank-aware, bucketed display** — "Strong / Good / Weak" from
  skills-coverage + title, never a raw comparable-looking % (scores aren't
  calibrated across jobs — ConFit / calibrated-distillation). **No
  applicant-percentile** ("top X%"): we have no applicant pool, so it would be
  invented. Detailed decision in [ADR-016](../decisions/ADR-016-bucketed-fit-display.md).
- **A lite, fast, local scoring engine** — skills-coverage ratio (instant, no
  model) drives the bucket; a fast local text-similarity (TF-IDF cosine, or a
  small embedding) computes the before/after **delta** that gives honest
  movement. Deterministic, no external call in the hot path; ESCO synonym list
  for cheap semantic matching; embeddings only if coverage proves insufficient.
- **Skills-coverage + exact-title as primary signals** (the dominant ranker
  features), over prose similarity.
- **Honest, teachable gaps** — split *"you have the skill but not the JD's
  word"* (fixable, truthfully) from *"you genuinely lack this"* (not fakeable).
  Movement/emotion lives here, not in a chased number. Ties non-negotiable #2
  (no "regenerate to greener").
- **Transparency = the wedge** — show top reasons in plain language (only 26%
  of candidates trust black-box AI scores; jobot's honesty differentiates).
- **Backend validation loop** — capture (score → outcome) pairs via "did you
  hear back?" as quiet ground truth; benchmark against TalentCLEF. Not a
  user-facing claim until data exists.

## How we'll know it worked

Re-scoring is stable (inherits REQ-015 determinism); users act on high buckets
(support KPI S3); gap language matches the JD's terms; over time, high buckets
correlate with real callbacks (ROC-AUC on collected outcomes).

## Related

REQ-015 (deterministic base), ADR-015 (single value archived),
ADR-016 (bucket display), ADR-017 (JD-language source of truth),
ADR-018 (engine: local rank A + LLM judge B), GOV-004 (scoring bias),
RESEARCH-market-thesis, RESEARCH-scoring-tech-landscape (validation + bake-off).

## Design status (2026-08-31)
Engine decided and validated via scoring bake-off (`scripts/scoring_bakeoff.py`,
5 approaches × real resumes × real JDs). Language handling = ADR-017; engine
shape = ADR-018. **Next:** 5→3→1 prompt iteration to reinforce
`semantic_score.py` (cross-language rule + coverage→bucket), then wire
`lite_score.py` as the local ranking layer. Cache/temp non-determinism mapped
in `next-work.md` (2026-08-31 entry) — fold `temperature→0` + text-hash cache
key into the same pass.
