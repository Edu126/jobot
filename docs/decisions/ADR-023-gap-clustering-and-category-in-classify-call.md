# ADR-023: Gap clustering + theme category ride the JD-free classify call

Date: 2026-09-02
Status: Accepted
Relates to: REQ-020 (tactical gap panel), ADR-022 (aggregation, tightens its
deferred-normalizer note), ADR-008 (prompt/cache conventions), GOV-005 (honesty)

## Context

REQ-020 wants the aggregated gaps (a) bucketed into 3 themes (technical /
certifications+languages / domain+experience) and (b) clustered so
near-duplicate phrasings ("Fluent French", "Bilingual French (CBC)") read as one
concept. ADR-022 explicitly deferred this ("a normalizer can tighten it later
without touching the cache shape"). Later is now.

## Decision

No new call site. Extend the existing JD-free classify prompt (ADR-022) to
return, per gap, two more fields: `category ∈ {technical, certifications,
domain}` and `canonical` (a short concept label, IDENTICAL across variants of
the same underlying requirement). The batched call already sees all distinct
gaps at once, so it can merge synonyms and cross-language variants — which
string-normalization can't. Persist both in `gap_classification`
(add `category`, `canonical` columns; bump `PROMPT_VERSION`). On incremental
renders, pass the already-cached canonical labels into the prompt as "reuse these
when a new gap fits one" — anchors clusters across calls at `temperature=0.0`.
`build_gap_map` groups real gaps by `canonical`, sums their counts, keeps the
member surface-forms for the popover, buckets by `category` (unknown → domain),
and returns top-5 per pillar. Register the changed output in `llm-surface.md`.

## Alternatives considered

- Embeddings + clustering: rejected — infra we don't run, for a handful of short
  strings the LLM already groups in-context for free.
- String normalization only: rejected — can't merge synonyms or cross-language
  variants, which is the whole point of clustering.

## Consequences

- Zero new LLM calls; only new distinct gaps ever cost a classification, cache
  makes repeat renders ~free (ADR-022 property preserved).
- `canonical` isn't 100% stable across incremental calls; the anchor-reuse hint
  + temp 0 keep it close, and a wrong merge is now user-correctable via ✕
  dismiss (ADR-024). The category is a coarse 3-way bucket by design.
