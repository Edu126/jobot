# REQ-026: Phase 0 — instrumentation + the stranger cohort

Date: 2026-09-07
Source: Eduardo (strategy session — the investor/stakeholder framing)
Status: Open

## What they asked for
"How do we collect the metrics? What are they?" — and, underneath the stakeholder
prep: prove the one thing we can't see today. We've built a rich product surface
(scoring, gap map, prep kit) for **4 friends** but skipped Phase 0. The roadmap
says Phase 0 = instrument, and it is the gate that earns "the right to make any
bet." We have no retention number.

## What they actually need
The right to choose a branch (product depth · persona · go-to-market) with
evidence instead of guessing. That requires two things, both cheap because the
BI/pulse loop already exists (`architecture/vision.md` non-negotiable #5):

1. **Surface the Phase 0 KPIs on `/admin/pulse`** — from `milestones.md`, do not
   invent new ones:
   - **G1 — Weekly returning users** (W1/W4 retention). *The number we can't see.*
   - **G2 — Applications completed / week.**
   - **S1 Activation** — % reaching first tailored artifact in session 1.
   - **S2 Artifact acceptance** — % of artifacts used with minimal edits.
   - **S3 Score trust** — do they apply to high-scored jobs?
2. **Wire the two missing captures:** a per-user return/session event (feeds G1),
   and the **outcome loop** ("did you hear back?") — the moat seed, not yet wired.

Then recruit **~10 strangers** (non-friends, actively job-hunting) by hand — "do
things that don't scale." A hard **feature freeze** holds while this runs: no
net-new user-facing features until the number exists.

## How we'll know it worked
`/admin/pulse` shows a real W4 retention figure for a cohort that isn't the
founder's friends — and we can state, with data, whether strangers come back.
Pre-commit the gate now: **≥N of 10 return in week 4 → greenlight a branch.**

## Related
- `product/milestones.md` (Phase 0 KPI definitions — the source of truth).
- Reuses existing signal tables (events, applications, viewed_jobs, feedback);
  one thin ADR for HOW return + outcome events are captured, when decided.
- REQ-027 (the page) is the top-of-funnel that feeds S1 activation; ships
  independently so metrics are never blocked by page polish.
