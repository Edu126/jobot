# ADR-031: "Refresh news" is gated to the fallback — not an always-on button

Date: 2026-09-05
Status: Accepted — **partially supersedes [ADR-027](ADR-027-company-outlook-persistent-cache-shared.md)**
(its user-facing "Refresh news intel" affordance)
Relates to: ADR-029 (Tavily cost), REQ-024 (shared quota pool), GOV-007

## Context
ADR-027 shipped "Refresh news intel" as the one sanctioned regenerate. But each
click spends a **Tavily search**, and the free tier is a **single pool shared
across all apps** (REQ-024). An always-visible refresh on every prep detail
invites repeated clicks for intel that is already cached and fresh-enough —
low value, real shared cost ("eats us alive").

## Decision
Remove the always-on button. In the normal grounded state the outlook renders
with **no refresh**. A one-off fetch (`?refresh=1`) appears **only in the
empty/fallback state**, where nothing is cached and a fetch is the only way to
get intel. The endpoint stays; only its always-visible entry point is gone.

## Alternatives
- Per-session cooldown: more UI/state to guard a rare spend.
- Remove refresh entirely: the fallback is the one place it genuinely helps.
- Auto-TTL: silent background spend against a shared pool is worse.

## Consequences
News can go stale in the grounded state with no manual override — accepted;
protecting a shared free-tier pool wins. Revisit once a paid tier + the REQ-024
admin panel give per-user quota visibility. ADR-027's cache/shape rules stand.
