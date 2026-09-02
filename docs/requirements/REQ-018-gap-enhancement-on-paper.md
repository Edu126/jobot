# REQ-018: Gap enhancement (on-paper) — from "here's your gap" to "here's your next move"

Date: 2026-09-01
Source: Eduardo (product architect) — first slice of REQ-017 Cluster A
Status: Building — mechanism decided (ADR-021), ready to implement

> First buildable slice of the REQ-017 "land it" stage. Cluster A, on-sequence
> (Phase 1). Bound by GOV-005 (enhance ≠ fabricate).

## What they asked for

From REQ-017 (2026-09-01): *"ahora cómo lo enhance (gap analysis)"* — the
enhance half of the post-apply stage. Resolved product decisions (2026-09-01):
lead with **Cluster A**; near-term depth is **on-paper only** (reword/surface
existing truths, honest); the course/coaching rev-share arc stays deferred to
Phase 3.

## What they actually need

We already compute `matched/gaps` at score time (REQ-016) and show the gaps.
But a gap list with **no next action** is exactly the blank-page,
high-cognitive-load moment the product vision exists to carry — it names the
problem and then abandons the user at it. The need is to turn each gap into a
concrete, *honest* move the user can make on their own résumé/profile **right
now**:

- Where a gap is really a **wording/visibility** problem (the user *has* the
  skill but the JD's exact-title language isn't on the page), surface it and
  suggest the rewording the AI ranker rewards — "be seen · be ranked · be
  real," never "beat the ATS" (vision non-negotiable).
- Where a gap is **real** (the user genuinely lacks it), say so plainly and
  honestly — do **not** invent it (GOV-005). The "close it for real" path
  (courses) is out of scope here, deferred to Phase 3.

This is the gap monetized on the first horizon ("on paper") and it seeds the
candidate persona with what the user affirms is true.

## Scope guardrails

- **In:** turn existing `matched/gaps` into per-gap, on-paper suggestions;
  honest "wording gap" vs "real gap" distinction; user acts on their own text.
- **Out:** course/coaching recommendations (Phase 3, governance-gated);
  LinkedIn profile eval (separate slice, next in Cluster A); anything that
  asserts a skill the user hasn't affirmed (GOV-005); a user-facing
  "Regenerate/Retry" escape hatch (fix quality in the contract layer instead —
  standing feedback).
- **Card density:** must not bloat the job card — gaps already render there;
  enhancement lives in the detail view, degrades gracefully when gaps are
  empty (standing feedback).

## How we'll know it worked

The thing that stops happening: a user looking at their `gaps` list with **no
next action**. Success = a user opens the gap-enhance view and makes at least
one concrete change to their own résumé/profile (or explicitly dismisses a gap
as not-worth-it) — a real edit, not a number on a dashboard.

## Related

REQ-017 (parent stage), REQ-016 (`matched/gaps` this builds on), GOV-005
(enhance ≠ fabricate — binding), product vision (gap monetized 3×; be seen·
ranked·real), milestones Phase 1. **ADR-021** — mechanism: reuse score-time
gaps + one lazy, cached classify/suggest call.
</content>
