# ADR-018: Bucketed scoring engine — local ranking (A) then LLM judge (B)

Date: 2026-08-31
Status: Accepted
Relates: REQ-016, ADR-016 (bucket display), ADR-017 (JD-language), RESEARCH-scoring-tech-landscape

## Context
ADR-016 chose bucket + gaps over a raw %. We still need the engine. A 5-approach
bake-off on real resumes × real JDs settled it: a local-only matcher undercounts
non-EN / cross-language (Andrea 0.07, Mehran-FR 0.10) while an LLM judge fixes it
(0.47 / 0.50) and stays honest on true gaps (Eduardo/AEC 0.00). JUDE research
points to the two-stage retrieve-then-rerank shape.

## Decision
Two layers, retrieve-then-rerank:
- **A = local ranking.** TF-IDF / skills-coverage (`lite_score.py`),
  deterministic, instant, no API. Orders the whole result list cheaply.
- **B = LLM judge.** On the surfaced top slice only: extract the JD's
  requirements, judge which the resume evidences (cross-language per ADR-017),
  coverage → bucket + gaps. **B is a reinforcement of the existing batched
  prompt** (`semantic_score.py`, batch=5) — add the cross-language rule and
  reframe output from a raw 0-100 to coverage→bucket; not a new call path.

Reject JUDE's serving stack (Kafka/Brooklin, ANN/IVFPQ, 7B distillation) —
scale-only, harmful at one-user scale.

## Consequences
- retrieve(A)→rerank(B) bounds LLM cost to the top slice, not every job.
- Determinism: scoring `temperature → 0` + cache keyed on (resume-text hash,
  JD, lang, prompt_version). Fixes the RAM/temp non-determinism mapped in
  next-work.md (Mehran's 3-different-scores).
  **Corrected by [ADR-019](ADR-019-gemini-scoring-nondeterministic-stability-via-cache.md):**
  temp=0 does NOT make Gemini deterministic (verified same-model drift ±3–10);
  user-facing stability comes from the cache freezing the first score, not from
  temperature. `temperature=0` is kept (lowest variance) but is no longer
  claimed to guarantee reproducibility.
- Buckets never shown as a raw comparable % (ADR-016 holds).
- `lite_score.py` becomes the A layer; embeddings deferred until A+B prove
  insufficient (REQ-016).
  **Deferred by [ADR-020](ADR-020-defer-lite-score-a-layer.md):** the score
  chain calls B on every job regardless, so an A-layer that only reorders adds
  cost without the promised cap. `lite_score` stays unwired until a real top-N
  limit is on the table; `affinity` (ADR-010) keeps ordering the batches.
