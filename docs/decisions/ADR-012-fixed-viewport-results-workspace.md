# ADR-012: Fixed-viewport results workspace — page stops scrolling, panes own their scroll

Date: 2026-08-26
Status: Accepted
Relates to: REQ-012
Supersedes (in part): the detail-pane positioning landed in `6b5dece`
(absolute pane + JS-computed `top`), which this removes.

## Context

The results page is a normal scrolling document. Inside it, the detail
pane has been fought over four times in one session (`3dcbc0b` sticky →
`3ebf9c4` items-start → `7696df1` fixed → `6b5dece` absolute + JS `top`).
Each attempt tried to pin a pane inside a moving document; the landing
version computes `aside.style.top` from the clicked card's bounding rect
on every click.

Sprint 8 then made the same document progressive: `/growth` appends cards
while the user reads, `/score-batch` swaps badges in place, the min-score
slider appears late. ADR-011's stability rules (append at end, never
re-sort) protect *list order* but not the *viewport* — the document still
grows under the reader.

Constraints that are real today: 4 real users, solo maintainer + AI pair,
FastAPI + Jinja2 + HTMX + Alpine with no build step (ADR-003), and a
`base.html` whose `<main>` is a plain flow container shared by every page.
The detail-pane markup, the `selectedJob` store and `job_card.html` are
shared with the `/jobs` top-matches section.

## Decision

Make the results page a **viewport-height app shell on `lg` and up**, and
leave everything below `lg` exactly as it is.

- `base.html` gains three template seams — `body_class`, `main_class`, and
  a `footer` block — so one page can opt into `lg:h-dvh lg:overflow-hidden`
  without changing any other page's layout.
- On the results page `<main>` becomes a flex column: compact header and
  filter toolbar are `shrink-0`; the workspace grid is `flex-1 min-h-0`.
- The grid is `lg:grid-cols-[minmax(0,32fr)_minmax(0,68fr)]`. Each column
  is its own `overflow-y-auto min-h-0` scroll container.
- The absolute-pane mechanism is deleted: the `position:absolute` +
  `width: calc(50% - 12px)` inline styles on `#jobs-detail-aside`, the
  `lg:relative lg:items-start` on the grid, and the ~10-line geometry
  block in `base.html`'s `selectedJob.select()`. In a fixed workspace the
  pane is just a grid cell, so there is nothing to align.
- A viewport shorter than ~560px keeps document scroll (the shell applies
  only above that floor) — otherwise both panes degrade to unusable slivers
  on short laptop screens.
- **Auto-select the first visible job on desktop only, and without marking
  it viewed.** `selectedJob.select(id, { markViewed })` gains the option;
  auto-selection passes `false`. Mobile never auto-selects — the sheet is a
  modal and would open over the list on load.

  The governing principle, in the product owner's words:

  > **Viewed = user engagement, not UI state.**

  This is broader than this feature and should outlive it. `viewed_jobs`
  feeds the `hideViewed` filter, the fresh-view breakdown counts, and the
  BI agent's funnel question ("search → view → save → tailor → apply").
  Anything the system does on the user's behalf — auto-selection today,
  a restored session or a prefetch tomorrow — must not write to it. Only
  a deliberate act by the user, sustained past the existing 3-second
  threshold, counts as a view.

Server contracts are untouched: `/jobs/results/{key}`, `/growth`,
`/score-batch`, `/jobs/detail/{id}`, the `jobs_meta` shape, the batch size
of 5, the server-side sort, and every OOB target id stay exactly as they
are. This is a template + shell change, not a routing change.

## Alternatives considered

- **Keep the document scrolling, just shrink the chrome.** Cheapest, and
  it does address complaints 1 and 2 — but leaves complaint 3 (the pane
  behaves like a separate floating thing) and leaves the JS geometry hack
  in place. Rejected: it treats the symptom the four previous iterations
  already failed on.
- **`position: sticky` on the detail pane.** Already tried and reverted in
  `3dcbc0b`/`3ebf9c4` — grid stretch silently breaks it. Rejected on
  evidence.
- **Make the whole app a fixed shell** (body overflow hidden globally).
  Rejected: profile, journey and the tailor flow are genuinely long
  documents. Opt-in per page via template blocks costs three lines.
- **Client-side re-sortable list (the `[Sort ▾]` control in the ask).**
  Deferred, not rejected. Re-ordering DOM nodes fights `/growth`'s
  `beforeend` append contract — any user sort would be re-scrambled by the
  next arrival. If it ships it must be gated on `discoveryComplete`, same
  as the min-score slider. Out of the first slice.
- **`100vh` instead of `100dvh`.** Rejected: mobile/tablet browser chrome
  makes `100vh` overflow. `dvh` with a `vh` fallback declaration.

## Consequences

- **What gets easier.** ADR-011's progressive model finally reads
  correctly: an appended card lands below a fold that does not move, and a
  badge swapping in place changes nothing about where anything is. The
  four-iteration pane problem disappears rather than being solved again —
  there is no geometry to compute. Long job descriptions stop dragging the
  card list downward.

- **What gets harder / accepted debt.**
  - `base.html` grows three template seams. Small, but they are now a
    contract other pages can reach for, and a page that sets `body_class`
    wrongly will silently trap its own scroll.
  - `min-h-0` on every flex/grid child is load-bearing and invisible.
    Omit it anywhere in the chain and the panes stop scrolling while the
    page starts to — the exact bug class this ADR exists to remove. It
    needs a comment at each site, not just here.
  - Nested scroll regions are an accessibility cost we are taking on
    deliberately: each pane needs `tabindex="0"` and an accessible name to
    be keyboard-scrollable at all, and the cards need real keyboard
    selection (they are mouse-only today — a pre-existing gap this layout
    makes worse, since the per-card action row is `lg:hidden`).
  - Auto-selection means the detail pane issues a `/jobs/detail/{id}`
    request on every results page load that previously issued none. One
    extra request per page view; acceptable at 4 users, worth remembering
    if the rate limit on that route ever bites.
  - `job_card.html` and the `selectedJob` store are shared with the
    `/jobs` top-matches section. Every change to either must be checked
    against that page, which does *not* have a workspace shell.

- **Non-goals still in force from ADR-010 and ADR-011.** No re-sort on
  score or card arrival. New cards append at end. Filter gate stays
  `discoveryComplete && pendingScoreCount === 0`. No concurrent LLM
  scoring, no `jobs.status` column, no WebSockets.
