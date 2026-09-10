# ADR-042: Remove the manual gap-map Rebuild — recompute is incremental + cached

Date: 2026-09-09
Status: Accepted
Supersedes: ADR-040 decision 4 (manual flush) and ADR-041 (flush guard)
Relates to: REQ-036, ADR-008 (economy), the "fix quality in the contract layer,
not with user-facing Regenerate/Retry buttons" principle

## Context

ADR-040 shipped a manual "Rebuild" button that deleted the résumé's cached gap
classifications and reclassified from scratch. It caused two problems:
1. It destroyed a good map when no LLM client was available (ADR-041 guarded that).
2. It is an **unbounded, user-triggered LLM cost vector** — each click is up to
   MAX_CLASSIFY_CHUNKS calls, repeatable at will ("nos quiebran si no hay
   límites" — Eduardo, 2026-09-09).

Its original justification (REQ-036 #3: Mehran's under-populated map) turned out
to be a *contract-layer* bug — classification never completing — which we fixed by
draining the whole filtered set on every render. With that fix, the map
self-populates correctly; a manual rebuild is no longer needed.

## Decision

Remove the Rebuild button, the `POST /profile/gap-map/flush` route, the
`gap-rebuild-unavailable` toast, `db.delete_gap_classifications`, the
`PROFILE_GAP_FLUSHED` event, and the related i18n. The gap map recomputes
**incrementally on each profile visit**: it aggregates counts in SQL (free) and
classifies **only gaps not already cached** — so repeat visits cost ~0 LLM, and a
gap is classified exactly once, ever (bounded to MAX_CLASSIFY_CHUNKS per visit
while catching up on newly-scored jobs). There is no all-at-once reclassification
path reachable by a user, so no rate-limit is needed. False positives remain
handled per-cluster by the ✕ dismiss (ADR-024).

## Alternatives considered

- Keep the button, rate-limit 1/day per résumé: rejected — adds state + a UI
  escape hatch the contract-layer fix made unnecessary (the design principle).
- Nightly/at-score-time classification so the profile view is pure-cache (never
  blocks on LLM): a real UX improvement (the visit can spin ~25s cold), but a
  separate perf change; deferred, not needed to remove the cost risk.

## Consequences

- No user action can trigger a full reclassification → the cost-abuse vector is
  gone.
- If a batch of classifications is ever systematically wrong (not just
  incomplete), fixing it is an admin/CLI/prompt-version-bump concern, not a user
  button.
- ADR-041's guard is moot (no flush to guard) and is superseded here.
