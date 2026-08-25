# REQ-008: Jobs Results filters must react to streaming score updates

Date: 2026-08-25
Source: Mehran (2026-08-25 PM feedback dump)
Status: Open

## What they asked for

> El filtro `min_score` no re-evalúa cuando llegan scores nuevos del
> batch chain. 3 de 31 visibles, refresh revela 21.
>
> El filtro "solo nuevas" oculta todo — filter roto.

Two concrete bugs on `/jobs/results`, both about client-side filters
losing sync with the state that HTMX is streaming in via OOB swaps
during the score-batch chain.

## What they actually need

The results page uses HTMX to progressively hydrate job cards with
scores (via `/jobs/results/.../score-batch` chained calls, one batch
per 5 jobs — see llm-surface.md site #1). Filters live in Alpine and
read from a `jobs_meta` store. The bug class is that when new score
data arrives via OOB swap, the Alpine store is not being updated (or
is being updated in a shape the filter predicate doesn't recognise),
so the filter's derived count freezes to whatever was hydrated on
initial render.

Effect for the user: they set a `min_score` of, say, 70; only 3 of
31 jobs qualify at first render; the batch chain finishes and 21
would qualify — but the user sees the stale 3 until they hit refresh.
Refresh is not a workaround; it defeats the point of streaming
scores. Same class of bug is what makes "solo nuevas" show zero —
the "new" flag is set server-side per-job, but if the store never
gets the update, the predicate matches nothing.

Fix has to keep the streaming architecture (no full re-render) and
must make the Alpine store the single source of truth after every
OOB swap. Two candidate mechanisms: (a) OOB swaps target a hidden
data island whose `@htmx:after-swap` handler mutates the store; (b)
each batch response carries a small `hx-trigger` payload that
Alpine listens on. Pick one — probably (a) — and document it as an
ADR so the pattern is reusable.

## How we'll know it worked

- Load `/jobs/results` for a 30-job search. Set `min_score = 70`
  immediately. Watch the visible-count number tick upward as batches
  arrive, without any manual refresh.
- Toggle "solo nuevas" on a search where at least 1 job is
  actually new — the correct set appears; toggling off restores the
  full set.
- No visible flicker or re-render of already-hydrated cards.
- Both filters continue to work after the batch chain completes
  (i.e. the store stays consistent, not just during streaming).

## Related

- llm-surface.md #1 (`_score_batch`) — the streaming source.
- ADR-003 (htmx + Alpine, no build step) — constrains the fix.
- Likely spawns a new ADR: "Alpine store hydration from HTMX OOB
  swaps."
