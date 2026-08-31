# ADR-020: Defer the lite_score A-layer — reorder-without-cap doesn't pay

Date: 2026-08-31
Status: Accepted
Relates: REQ-016, ADR-010 (affinity), ADR-018 (corrects its "lite_score becomes the A layer" consequence)

## Context
ADR-018 named `lite_score.py` as the local ranking (A) layer that would gate the
LLM judge (B), "bounding LLM cost to the top slice." We wired `lite_score.rank()`
into the `/score-batch` route, then examined the actual flow: the batch chain
auto-continues (`hx-trigger="load delay:200ms"`) until every uncached job is
scored. So ranking **reorders which jobs B scores first but scores them all
anyway** — the cost bound was never implemented (retrieve-then-*reorder*, not
retrieve-then-*limit*).

## Decision
Roll back the wiring: `/score-batch` keeps the cheap ADR-010 token-`affinity`
sort. `lite_score.py` + `rank()` stay in the repo, **unwired**, reused by the
bake-off. Reconsider only if/when we commit to a real top-N cap (LLM-score the
top slice, lazy/skip the rest) — a UX change (breaks "every job gets a score")
that needs its own decision.

## Consequences
- No LLM-call change (the chain already scored everything); we shed the added
  cost of a TF-IDF fit per job re-run every batch (~hundreds/search) for zero saving.
- No quality loss at the ordering step: `lite_score`, being a local string
  matcher, is as cross-language-blind as `affinity` (ES résumé vs EN JD → ~0
  coverage), so it never improved the case we most care about.
- ADR-018's engine (rank-then-judge, coverage-anchored B) and ADR-017
  (cross-language in B) stand; only the "A-layer now" consequence is deferred.
- The real cost lever, if needed later, is the top-N cap — filed as future work.
