# ADR-024: The ✕ dismisses a gap cluster — user override, persisted

Date: 2026-09-02
Status: Accepted
Relates to: REQ-020 (tactical gap panel), ADR-023 (clustering), ADR-022
(aggregation), product vision (career-persona seed)

## Context

REQ-020 gives each gap pill a ✕. The spec framed it as "un-group or delete";
resolved decision 2 cut v1 to **dismiss only** — un-grouping a term (splitting a
cluster, re-counting) opens questions not worth v1. Dismiss needs to persist so
a killed false positive stays gone across renders, and it is the first piece of
user-authored correction on the derived gap object (the persona seed).

## Decision

New table `gap_dismissals(resume_hash, lang, canonical, created_at)`, PK
`(resume_hash, lang, canonical)`. `build_gap_map` filters out any cluster whose
`canonical` is dismissed. Route `POST /profile/gap-map/dismiss` takes the
`canonical` label and upserts a row; Alpine removes the pill locally and fires
the POST (optimistic — the map is derived, nothing is lost if the request
races). Keyed on `resume_hash` (v17 convention) so a dismissal survives
re-render and an identical re-upload; editing the résumé changes the hash → a
fresh gap set, which is correct (the gaps themselves changed).

## Alternatives considered

- Dismiss by raw gap string (not canonical): rejected — the user dismisses the
  *concept* they see in the pill; killing one variant would leave siblings.
- Global (not lang-scoped) dismissal: rejected for v1 — `canonical` is
  language-specific, so cross-lang mapping would need its own key. Accepted
  limitation: flipping UI language loses the dismissal (noted).

## Consequences

- One small table + one route; no LLM, no new PII, no external surface — data
  stays in the local single-tenant DB, so no new GOV note beyond GOV-005 (which
  dismiss doesn't touch — it removes a flag, never fabricates one).
- A dismissal is a manual override on top of the AI classification; if the model
  later stops flagging that gap, the stale dismissal simply matches nothing.
