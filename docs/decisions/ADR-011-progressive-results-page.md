# ADR-011: Progressive results page — early redirect + auto-append during discovery

Date: 2026-08-26
Status: Accepted
Supersedes (in part): ADR-010 (reverses the "Truly concurrent discovery + scoring" non-goal)
Relates to: REQ-011

## Context

Sprint 8 slices 1-4 shipped. Real user testing surfaced that "feels
alive" is only half-delivered: because per-source discovery still
waits for the slowest source (LinkedIn, ~15s in practice) before
redirecting, users stare at a loading page for the full wait — even
though the fast sources (Indeed, Google) return in under a second and
often return 0 anyway. On today's scraper reality (LinkedIn ≈ only
site that reliably produces results — see live probe 2026-08-26)
this means the loading page shows "Found 0 · still searching…" for
14 of the 15 seconds. Honest, but not alive.

ADR-010 explicitly *rejected* concurrent discovery + UI:

> **Truly concurrent discovery + scoring** (worker appends to cache
> while UI polls): rejected — cards popping in below what the user
> is reading creates state-management debt no observed bug demands.

Real use has now supplied the observed bug: users watch a static
loading page for most of the wait, then land on a fully-scored page
all at once, defeating the "progressive intelligence" north star from
REQ-011. Time to reverse the non-goal.

## Decision

Ship progressive results in two tight phases:

**5a — Early redirect + banner.**
- Loading-status polling redirects to the results page as soon as the
  cache has ≥ 1 job, not only when the discovery task is done.
- The results page detects "discovery still running" by looking up a
  running `search_tasks` row keyed on `cache_key` (added to the task's
  payload at creation).
- A subtle banner tells the user "Still finding more jobs…" while
  discovery continues.
- The min-score filter gate (from Slice 4) now requires BOTH
  `discoveryComplete` AND `pendingScoreCount === 0` — otherwise the
  slider could flicker in during a lull between sources.

**5b — Auto-append via /growth endpoint.**
- New endpoint `GET /jobs/results/{cache_key}/growth?since=<count>`
  returns HTML card fragments for cache jobs at index >= since, plus
  a `jobs_meta` patch script for filter reactivity.
- Results page polls `/growth` every 2s while discovery is in flight.
  New cards **append at the end of the current DOM** (never insert
  mid-list — see stability rules below).
- When `/growth` reports discovery-done AND has no more jobs, it
  returns a terminator that stops polling and fires `onDiscoveryDone()`
  on the results page (sets `discoveryComplete = true`, hides banner,
  enables filter gate).
- When new cards land, the score-batch chain is re-triggered (an
  additional `<div hx-get="…/score-batch" hx-trigger="load">` is
  included in the growth response) so newly-added jobs get scored
  without a page reload.

## Alternatives considered

- **Redirect-then-reload-when-done**: land user on results page early,
  then when discovery task hits done → full page reload. Simple, but
  scroll position + Alpine state get blown away, and the user's
  in-progress reading of the first cards is disrupted. Rejected.
- **Explicit "Show more" button when discovery done**: user has to
  click to see new cards. Zero pop-in. But defeats "feel alive" —
  cards discovered while user was reading are invisible until an
  explicit action. Rejected.
- **Poll-and-insert-in-affinity-order**: mid-list insert to preserve
  global affinity sort. This is exactly the pop-in-under-cursor
  antipattern ADR-010 rejected. Kept rejected here — we append at end
  instead.
- **WebSockets / SSE for discovery events**: real-time is nice but
  needs infra change (uvicorn config, worker signalling). HTMX polling
  every 2s is enough for a 15s discovery window. Rejected as
  premature.

## Consequences

- **What gets easier.**
  - TTFJ (Time to First Job): drops from ~15s to ~1s for a search
    where any source returns fast. Even if only LinkedIn works,
    Indeed's empty response comes back in <1s and triggers the early
    redirect — the user lands on the results page with an empty state
    that says "Still finding more…", which reads better than staring
    at a loading spinner.
  - The Slice 4 filter gate becomes more honest: "all scored" now
    requires discovery to actually be complete, so no misleading
    "everything's done" state during a lull.

- **What gets harder / accepted debt.**
  - Stability rules ADR-010 wrote are amended, not discarded:
    - **New cards APPEND at end of current DOM.** Never mid-list.
      This is the rule that keeps user's reading position stable.
    - **No re-sort on card arrival OR on score arrival.** Score
      badges update in place; new cards land at end. If the user
      wants a re-sort, they reload.
    - **Filter gate = `discoveryComplete && pendingScoreCount === 0`.**
      Slider stays hidden until BOTH are true.
  - Two polling loops on the results page during discovery (growth +
    score-batch chain). Both self-terminate. Modest network load
    (~2 requests / 2s for ≤15s).
  - The score-batch chain must handle the "new pending jobs appeared
    after I thought I was done" case. Growth endpoint's re-trigger div
    covers it, but adds a small window where a score-batch could fire
    with 0 pending (returns immediately, no harm).
  - `search_tasks.payload_json` now stores `cache_key`. Set at task
    creation in `/jobs/run`. Backwards-compat: `get_running_by_cache_key`
    returns None for legacy rows without the field — those searches
    just get the old "wait for full discovery" behavior on refresh,
    no crash.

- **Non-goals still in force from ADR-010 unless explicitly reversed
  here.** Specifically: no concurrent LLM scoring batches, no
  `jobs.status` column, no TF-IDF retrofit for affinity, no origin
  tagging, no source diversity heuristic. Those remain deferred.

- **Success measured**, same events as REQ-011 — TTFJ should show a
  step-change in the Pulse baseline once this ships. If it doesn't,
  something's wrong.
