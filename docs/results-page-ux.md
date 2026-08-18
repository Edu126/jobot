# Results Page Flow — UX Redesign

**Status:** design doc, no code yet.
**Date:** 2026-08-18
**Related:** [working-plan.md](./working-plan.md), [search-cache.md](./search-cache.md).

## 1. Problem restated

The current page renders instantly but then behaves as if it's empty for
10-30 seconds because unscored cards are hidden by the `minScore ≥ 60`
filter. The header stat ("30 from cache · 50 scoring…") doesn't help the
user understand whether they should wait, browse, or refresh — it's a
status line pretending to be information.

## 2. Proposed model — three visible states

Give the user a mental model with clear phase names, surfaced in the
header:

- **`evaluating`** — first render; at least one card is still pending a
  score. The user is told "we're ranking these against your resume;
  here's what we have so far."
- **`ready`** — all cards scored. The header switches to a pure filter
  summary.
- **`expanded`** — a follow-on expand pass merged new jobs in. Same as
  `evaluating` or `ready` but with a badge noting recency.

The one number that always matters is **visible**. Everything else is
context.

## 3. Concrete recommendations

### 3.1 Header stats

**Current:** stacks 2-4 numbers with `·` separators, no anchor on what
"50 scoring" means for the user.

**Proposed:** lead with `X of Y visible`, then a small secondary line
about scoring progress with a thin progress bar. Two lines, not one.

Why: the primary decision the user makes on this page is "is there
anything worth clicking?" That's answered by `visible`. Scoring progress
is diagnostic, not primary — demote it visually.

Tradeoff: two-line header takes more vertical space. Worth it.

### 3.2 Default filter value

**Current:** `minScore = 60` applied from page load.

**Proposed:** **default filter to 0 while evaluating; snap to 60
automatically when all scoring completes** — with a small toast:
*"Filtered to score ≥ 60 · 15 hidden · show all?"* The user can dismiss
the auto-filter with one click.

Why: the value of `minScore=60` is "hide junk after we know what junk
is." Applying it before we know anything hides everything. This
preserves the intent (junk hidden by default on the settled page)
without punishing the loading state.

Tradeoff: user sees more low-score cards mid-load. Acceptable — they're
visibly ordered by score, so junk sinks naturally, and the auto-filter
arrives before they've clicked much.

### 3.3 Card visibility while pending

**Current:** hidden entirely (score=0 < minScore=60).

**Proposed:** **compact one-line skeleton rows** at the bottom, rendered
dimmed with a spinner and the title only. As each scores, it swaps to a
full card AND animates into its sorted position.

Why: shows honest activity ("we have 50 jobs, we're evaluating them")
without asking the user to visually parse a wall of 50 cards they can't
act on yet. One-liners keep the scannable list scannable. Rejected
alternatives:

- *Hidden (current)*: reads as "no results."
- *Full dimmed cards*: 50 grey cards is a wall; users won't scroll past.
- *Separate pile*: forces the user to context-switch. Also doubles the
  filter surface.

Tradeoff: two card shapes to maintain (compact skeleton + full card).
Small.

### 3.4 Scores streaming in

**Proposed:** **fade + slide-in when a card enters the visible set**,
using Alpine's `x-transition`. No pill, no user action.

Why: a "N new matches — show" pill is more control than the value
warrants; the user isn't making a decision, they're just watching a list
settle. Cards fading in for ~200ms signals "the list is alive" without
moving the user's scroll position dramatically. Only cards that clear
the *current* filter animate in — everything below stays quiet.

Tradeoff: motion is a11y-sensitive. Respect `prefers-reduced-motion` and
drop the animation for those users.

### 3.5 Sort stability

**Proposed:** **re-sort once, when scoring completes** (transition from
`evaluating` → `ready`). During evaluation, keep insertion order stable.

Why: re-sorting after every batch is disorienting mid-scroll. Not
re-sorting at all leaves the user with a wrong-looking list forever. A
single settle at the end is the honest compromise. Announce it lightly:
brief flash of the sort icon, or the "auto-filtered" toast doubles as
the "list settled" moment.

Tradeoff: for the first ~30s users see a not-yet-optimal order. That's
fine — they can already see which cards are ranked (badges have real
scores) and which are still evaluating (spinners).

### 3.6 Expand "done" behavior

**Proposed:** **Refresh button stays, but relabel it "Show new jobs"**
and, on click, do a **soft reload with `#new` anchor** that scrolls to
the first newly-added job. Add a temporary "new" badge (matching the
"New" 48h chip that exists) on the actually-new-to-this-search cards for
the session.

Why: an in-place HTMX merge is complex and doesn't buy much — the cache
already has the merged list, so a page reload IS the merge, and lazy
scoring means the reload is cheap (only genuinely-new jobs will show
spinners; the rest hit cache). Anchor + badge orients the user to what
changed.

Tradeoff: the "new" badge is per-session; if they refresh again, it's
gone. Acceptable — expand is a discrete event.

### 3.7 Edge states

- **Fresh search, 0 cached, filter would hide everything:** with §3.2
  (default filter=0 during evaluation), this doesn't happen. User sees
  compact skeleton rows immediately with title/company visible.
- **Quota exhausted mid-batch:** spinners on remaining unscored cards
  convert to a small `"—"` badge with a subtle amber outline. Header
  adds: *"Scoring paused — 12 jobs waiting until tomorrow."* No red, no
  scary error. Give the user a "show unscored anyway" toggle so they
  aren't blocked from browsing what we couldn't rank.
- **No resume uploaded:** don't score at all, don't show spinners, don't
  apply the score filter. Header: *"Upload a resume to rank these
  against your background."* Link to `/profile`. Cards render fully with
  `—` badges but are NOT hidden.

## 4. Copy — header string matrix

Two-line header. Primary line, then a `text-body-muted` secondary line.

| State | Primary | Secondary |
|---|---|---|
| Fresh, 0 cached | **Ranking 30 jobs against your resume** | *0 ranked · 30 to go · this takes about a minute* |
| Mid-scoring | **12 of 30 visible · ranking the rest** | *18 ranked · 12 still evaluating* + thin progress bar |
| All scored, filter on | **15 of 30 visible** | *Filtered to score ≥ 60 · 15 hidden · [show all]* |
| All scored, no filter | **30 jobs** | *All ranked · sorted by fit* |
| Expanded, mid-rank | **12 of 60 visible · ranking new jobs** | *30 already ranked · 30 new (18 still evaluating)* |
| Expanded, done | **28 of 60 visible** | *30 new jobs added · filter score ≥ 60 · [show all]* |
| No resume | **30 jobs** | *Upload a resume to rank these — [Profile]* |
| Quota out mid-run | **20 of 30 visible** | *Scoring paused — 10 waiting for tomorrow's quota · [show unscored]* |

## 5. Wireframe sketches

**Fresh-loading (t=0)**

```
┌────────────────────────────────────────────────────────┐
│ Junior PMO Coordinator                                 │
│ Ranking 30 jobs against your resume                    │
│ 0 ranked · 30 to go · this takes about a minute        │
│ ▓░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%                         │
├────────────────────────────────────────────────────────┤
│ [○ ] Project Coordinator · Acme                        │  ← skeleton
│ [○ ] BIM Coordinator · Beta                            │  ← skeleton
│ [○ ] Site Coordinator · Gamma                          │  ← skeleton
│ ...27 more compact rows...                             │
└────────────────────────────────────────────────────────┘
```

**Mid-scoring (t=15s)**

```
┌────────────────────────────────────────────────────────┐
│ Junior PMO Coordinator                                 │
│ 12 of 30 visible · ranking the rest                    │
│ 18 ranked · 12 still evaluating                        │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░ 60%                        │
├────────────────────────────────────────────────────────┤
│ [92] Senior PMO Coordinator · Acme     · Ottawa · 2d   │  ← full card
│ [87] Project Coordinator (I) · Beta    · Ottawa · 1d   │  ← full card
│ [74] BIM Coordinator · Gamma           · Kanata · 4d   │  ← full card
│ [○ ] Site Coordinator · Delta                          │  ← skeleton
│ ...11 more skeletons...                                │
└────────────────────────────────────────────────────────┘
```

**All-done (t=45s, after auto-filter snap)**

```
┌────────────────────────────────────────────────────────┐
│ Junior PMO Coordinator                                 │
│ 15 of 30 visible                                       │
│ Filtered to score ≥ 60 · 15 hidden · [show all]        │
├────────────────────────────────────────────────────────┤
│ [92] Senior PMO Coordinator · Acme     · Ottawa · 2d   │
│ [87] Project Coordinator (I) · Beta    · Ottawa · 1d   │
│ [82] PMO Analyst · Epsilon             · Nepean · 3d   │
│ ...12 more...                                          │
└────────────────────────────────────────────────────────┘
```

## 6. Implementation notes

**1-liner / trivial (~15 min each):**
- Change `minScore` default to `0` on page load; snap to `60` when
  `pending_score_count === 0`.
- Update header copy strings to the matrix above.
- Respect `prefers-reduced-motion` on card fade-in.
- Auto-scroll to `#new` on post-expand reload.

**Afternoon (~2-4h):**
- Compact skeleton row template (`partials/job_card_skeleton.html`) —
  title + company only, dimmed, with the existing spinner badge.
  Swap-out to full card via OOB when scored.
- Two-line header with progress bar (Alpine reactive to
  `pending_score_count`).
- "Auto-filtered · show all" toast that fires when the last score
  arrives.
- Alpine `x-transition:enter` on cards passing the filter.
- Sort-once-on-completion: after last batch OOB, trigger a client-side
  re-sort of the DOM by score (Alpine can do this by re-rendering from
  the reactive `jobs` array).

**Bigger rework (~1 day):**
- "Show unscored anyway" toggle for the quota-exhausted state — needs a
  separate filter dimension and a small state machine for
  `scoring_status` (`ready` / `evaluating` / `paused` / `disabled`).
- Session-scoped "new" badge for post-expand cards — needs a
  `first_seen_in_this_cache` field on cache pointers, or a client-side
  diff via sessionStorage against the pre-expand id list.

**Not recommended:**
- In-place HTMX merge on expand-done. The reload path is cheaper than
  the code cost, especially with lazy scoring making reloads cheap.
- Server-side pagination. Lazy scoring + compact skeletons for pending
  jobs achieves the same perceived-speed win without breaking the
  client-side filter model.
