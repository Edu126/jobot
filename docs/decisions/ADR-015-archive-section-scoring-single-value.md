# ADR-015: Archive section-based scoring — back to a single LLM value

Date: 2026-08-27
Status: Accepted
Supersedes: [ADR-006](ADR-006-section-based-scoring-llm-evidence-backend-math.md)
Archives (in implementation): REQ-004 (section scoring), REQ-005 (grounding guard-rail)

## Context

ADR-006 moved scoring to five fixed-weight sections with a runtime
grounding guard-rail (REQ-005), to buy determinism by giving the model a
rubric to reason against instead of a number to pick. In practice it did
the opposite: the grounding check required every word of a matched
*summary phrase* to appear in the resume, so it silently dropped ~100% of
scored jobs — results pages "loaded" forever (visible to all 4 users for
two days). Even patched, the section machinery is more surface area than
the value it returns: the UI only ever shows one overall score.

## Decision

Revert to the original single-value model: the LLM returns one 0-100
score + one-sentence reasoning + top matched/gaps per job; the backend
derives only the verdict band (ring colour). Remove sections, weights,
`hard_requirements`, and all grounding code. Keep the domain-neutral
persona (ADR-013), language plumbing, batching, and versioned cache; bump
`PROMPT_VERSION`/`SCORING_VERSION` to flush section-scored rows lazily.
`ScoreResult`'s top-level fields are unchanged, so card + detail UI are
untouched. Non-determinism run-to-run is accepted for now (cache makes it
stable per job+resume).

## Consequences

Scoring works again and the code shrinks. We lose the per-section
breakdown and the grounding backstop against hallucinated matches — an
accepted interim cost. The proper deterministic redesign is deferred to a
future REQ, fed by `docs/research/RESEARCH-scoring-approaches.md` (which
recommends LLM label-classification → fixed anchor scores). ADR-005
(quality in the contract layer) still holds — we fix quality in the
prompt, not with user escape hatches.
