# ADR-038: Keep the numeric 0-100 score, verdict-tinted — not a bare bucket

Date: 2026-09-08
Status: Accepted
Relates: [ADR-016](ADR-016-bucketed-fit-display.md) (superseded — bucket-only display),
[ADR-018](ADR-018-bucketed-scoring-engine-rank-then-judge.md) (coverage-driven engine),
[ADR-019](ADR-019-gemini-scoring-nondeterministic-stability-via-cache.md) (cache stability),
REQ-016

## Context

ADR-016 rejected showing a raw number: back then the score was an uncalibrated
gut-number that moved run-to-run and invited "regenerate until greener" gaming.
It proposed a bare Strong/Good/Weak bucket instead. That objection is now stale.
Post ADR-018 the 0-100 is **anchored to requirement coverage** (evidenced ÷ total
JD requirements), and ADR-019 caches it — so the same résumé × job lands the same
number. It no longer drifts, so number-chasing does not pay. The shipped UI
(`ring.html`, REQ-014) has all along rendered the coverage number inside a
verdict-tinted ring; the code and ADR-016 contradicted each other.

## Decision

Keep the live behavior: show the **numeric coverage score (0-100) inside a
verdict-tinted ring** (`score_ring`), with matched/gaps in the detail. The
verdict band supplies the honest "Strong/Good/Weak" read via color; the number
adds precision the coverage anchoring earns. We still **never** claim an
applicant-percentile ("top X%") — we have no applicant pool; the number is
coverage against the JD, nothing more. That guardrail from ADR-016 survives.

## Consequences

- Doc now matches code; ADR-016 marked superseded.
- Number is defensible because it is coverage-anchored + cached, not a gut value.
- If a future engine change de-anchors the score, revisit — the honesty rests on
  the coverage anchoring, not on the ring itself.
