# REQ-028: Fleet view — per-user drill-down, daily/weekly trends, funnel-evolution matrix

Date: 2026-09-08
Source: Eduardo (reading the fleet-pulse dashboard)
Status: Open

## What they asked for
Verbatim: "en mi view grande de admin, si quiero ver el detalle de usuario, tipo
un trend que pueda ver diario y semanal, de datos agregados, pero me gustaría
poder filtrar per user, o/y tener una matriz per user con los main KPIs del
funnel para ver evolución."

So, on top of the fleet-pulse rollup + table (REQ-026 / ADR-035):
1. **Per-user drill-down** — click/expand a user to see their detail.
2. **Daily AND weekly trends** of the aggregated metrics (not just a current value).
3. **Filter by user.**
4. **A per-user funnel matrix** (main KPIs × time) to read *evolution*, not a snapshot.

## What they actually need
The current KPIs are a **snapshot** (one number per app). To read whether a user
is *warming up or cooling off* you need the metrics **bucketed over time** and
**per user**. The raw tables already carry timestamps (`events.ts_utc`,
`applications.applied_at`, `job_scores.scored_at`), so day/week buckets can be
computed **on demand** — no new history store, works retroactively.

Concretely:
- Add a **time-series** computation next to `compute_phase0_kpis`: per bucket
  (day or week) the funnel + engagement counts — sessions/active, jobs viewed,
  saved, applied, tailored, heard-back. Emit it from the KPI CLI so fleet-pulse
  can pull it per app.
- **fleet-pulse** renders, per user: a **funnel-evolution matrix** (rows = weeks,
  cols = viewed → saved → applied → heard-back) + **daily and weekly sparklines**
  of the key lines, reachable by a **per-user filter / drill-down** from the table.

## How we'll know it worked
From the big fleet view, Eduardo picks one user and sees — without opening that
app — how their funnel moved week over week (e.g. "viewed 40 → saved 8 → applied
3 last week, heard back on 1") plus a daily activity line, and can filter the view
to just that user. A cooling-off user is visible as a falling line, not inferred.

## Related
- Extends REQ-026 / ADR-034 (deterministic KPIs) + ADR-035 (fleet pull).
- Needs a new ADR when built: **time-series computed on demand from raw tables**
  (vs snapshot accumulation) — the recommended approach; decide at build time.
- Reuses existing series helpers in `core/events.py` (daily_activity, funnel).
