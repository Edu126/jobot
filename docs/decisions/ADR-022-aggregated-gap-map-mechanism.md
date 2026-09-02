# ADR-022: Aggregated gap map — dedup + JD-free per-gap classification, cached

Date: 2026-09-02
Status: Accepted
Relates to: REQ-019 (gap map), REQ-018 / ADR-021 (per-job enhance, complement),
GOV-005 (enhance ≠ fabricate), ADR-008 (prompt/cache conventions)

## Context

REQ-019 wants all of a candidate's **real** gaps in one cross-job section,
ranked by how many target roles they block. Per-job enhancement (ADR-021) is
JD-specific and lazy — wrong shape for a candidate-level view, and re-running it
per job would be N LLM calls. We already store every job's `gaps` in
`job_scores`.

## Decision

Compute the map from cached `job_scores`: gather every gap across the résumé's
scored jobs and **count frequency** (pure SQLite, no LLM). Then classify each
**distinct** gap **JD-free** — résumé × gap → `{kind: wording|real, suggestion}`
— in **one batched LLM call**, not per job. This differs from ADR-021 (which
judges against a specific JD); the map asks only "does the résumé evidence this
anywhere?". Cache per-distinct-gap in `gap_classification(resume_hash, lang,
gap, prompt_version)` so it's reused across renders and only new gaps cost a
call. The map shows **real** gaps ranked by count (with the defense hook);
wording gaps stay per-job (ADR-021). `temperature=0.0`; register in
`llm-surface.md`.

## Alternatives considered

- Re-run per-job enhance for every job: rejected — N calls, JD-specific noise.
- Aggregate raw gap strings with no classification: rejected — can't tell a
  wording gap from a real one, which is the whole point.
- One giant per-résumé prompt each render: rejected — the per-gap cache makes
  repeat renders nearly free and only classifies newly-seen gaps.

## Consequences

- One new LLM call site (batched over new distinct gaps, cached) — modest,
  quota-aware. Add to `llm-surface.md` (ADR-008).
- Frequency ranking is only as good as gap-string dedup; near-duplicate phrasings
  ("PMP", "PMP certification") count separately until normalized — acceptable
  first cut, a normalizer can tighten it later without touching the cache shape.
- Map quality inherits `job_scores` quality; consistent with the per-job view by
  construction (same source gaps).
</content>
