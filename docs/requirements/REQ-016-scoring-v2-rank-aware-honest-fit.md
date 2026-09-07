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
shape = ADR-018.

**Done (2026-08-31, B-layer pass):** the 5→3→1 prompt iteration reinforced
`semantic_score.py` — the 0-100 is now anchored to requirement COVERAGE
(extract → mark evidenced/missing → coverage→band) and the cross-language
rule + single fixable wrong-language gap are taught by few-shot (ADR-017).
`PROMPT_VERSION` bumped to `2026-08-31-coverage-crosslang` (logically
invalidates old rows). Determinism folded in the same pass: scoring runs at
`temperature=0.0` (per-call override on `generate_json`, generation stays
0.4), and the score cache is re-keyed on the resume **text hash** (schema
v17) so a regenerated-but-equivalent resume reuses its scores — fixes
Mehran's unstable re-score (next-work.md).

**A-layer: tried then ROLLED BACK ([ADR-020](../decisions/ADR-020-defer-lite-score-a-layer.md)).**
`lite_score.rank()` was wired at the score-batch boundary, then reverted: the
batch chain scores every job anyway, so ranking only reordered (no LLM-call
saving) at higher CPU, and being a local string matcher it's as cross-language-
blind as the existing `affinity`. `affinity` (ADR-010) keeps ordering the
batches; `lite_score.rank()` stays in the repo unwired until a real top-N cost
cap is on the table.

**Validation (human-in-the-loop), now BATCH-of-5 (production path):**
`scripts/scoring_bakeoff.py --ab` scores the real fixtures in batches of 5 (OLD
gut vs NEW coverage+cross-language, temp=0) → `data/ab_scoring_<date>.md` with
per-finding checkboxes + notes. `--determinism` runs the same batch N× (no
cache). Findings 2026-08-31: (a) batch composition itself shifts scores (Mehran
AEC 88 solo → 75 in a batch), (b) NEW is consistently less drifty than OLD
(spread 3-5 vs up to 20 w/ verdict flip), (c) cross-language wins clear in batch
— Andrea EN 45→62, wrong-language gap firing for Andrea/Sara. Eduardo is the
ground-truth judge; marks still pending = the real go/no-go on the prompt.

**Still open** (next-work.md): persist gemini exhaustion/request counts to DB
(the other half of Mehran's model-fallback divergence); the regen truncation
bug (separate from scoring); optionally extend coverage-ranking to the static
first-paint render order (currently token-affinity).
