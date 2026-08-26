# REQ-012: Job Hunting Results Workspace

Date: 2026-08-26
Source: Eduardo (product architect), written as a full REQ + SA review request
Status: Open

## What they asked for

> "Redesign the Job Results view from a vertically scrolling search-results
> page into a fixed-height Job Hunting Workspace optimized for browsing,
> comparing, and analyzing opportunities."
>
> "The Results screen should feel like a workspace, not a long webpage."
>
> "Left = discover and compare jobs. Right = understand and act on the
> selected job."

Named problems, in their words:

1. "The header/search context consumes too much vertical space."
2. "Filters occupy a disproportionately large area."
3. "The results area behaves like a normal page while the selected job
   detail behaves like a separate floating/scrolling panel."

Named target behaviours:

- Fixed viewport; the page itself stops scrolling. The two panels scroll
  independently.
- Roughly 30–35% list / 65–70% detail, not 50/50.
- Auto-select the first available job — no empty "click a job" state.
- List order stays stable while progressive scores arrive.
- Filters become a compact toolbar, not a card.
- Match Score filter stays gated on discovery-complete AND all-scored.
- Narrow viewports must not get a squeezed 30/70 split.

Explicitly framed as "a UI/workspace restructuring," with a do-not-introduce
list: no new job model, no status state machine, no new scoring or matching,
no concurrent LLM scoring, no WebSockets, no frontend framework, no separate
detail-page architecture.

## What they actually need

The ask and the need are close but not identical, and the gap matters.

The **ask** is a layout: fixed height, two panes, 30/70.

The **need** underneath is *positional stability during asynchronous
arrival*. Sprint 8 (ADR-010, ADR-011) made the results page progressive —
cards append while the user reads, score badges swap in place, the min-score
filter appears late. Every one of those events happens inside a document
that scrolls as one column, so the user's frame of reference moves under
them. The four-iteration detail-pane saga (`3dcbc0b` → `3ebf9c4` →
`7696df1` → `6b5dece`) is the visible symptom: each attempt tried to pin a
pane to a moving document, and the landing solution — absolute positioning
with JS-computed `top` — is a workaround for a page that should not have
been scrolling in the first place.

So the fixed-height workspace is not a cosmetic preference. It is the
layout that makes ADR-011's progressive model legible: when the viewport is
fixed and each pane owns its scroll, "a card appended below the fold" and
"a badge changed in place" are both invisible non-events instead of
things that move the reader's content.

Two things the ask leaves implicit that we should treat as part of the need:

- **Auto-select must not count as reading.** A selection the user did not
  make should not fire the 3-second viewed-tracker, or the `hideViewed`
  filter and the fresh-view counts start lying.
- **Desktop-only for the fixed layout.** Below `lg` the detail pane is a
  bottom sheet, not a column; auto-selecting there would open a modal over
  the list on page load.

## How we'll know it worked

The user browses a results page from top to bottom, clicks through several
jobs, and reads a long job description — and the browser scrollbar on the
document never moves. Cards arriving from `/growth` and badges arriving
from `/score-batch` do not shift anything the user is currently looking at.

Secondary, from the existing REQ-011 instrumentation: no regression in TTFJ
or TTFS. This is a layout change; it must not cost time-to-first-job.

## Related

ADR-012 (proposed) — fixed-viewport workspace shell; retires the
absolute-positioned detail pane from `6b5dece`.

Depends on and must not violate: [ADR-010](../decisions/ADR-010-progressive-hunting-async-per-source-affinity.md),
[ADR-011](../decisions/ADR-011-progressive-results-page.md) — specifically
the append-at-end and no-re-sort stability rules.
