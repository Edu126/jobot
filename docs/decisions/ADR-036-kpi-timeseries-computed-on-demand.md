# ADR-036: KPI time-series is computed on demand from raw tables (no snapshot store)

Date: 2026-09-08
Status: Accepted
Relates to: REQ-028, ADR-034 (deterministic KPIs), ADR-035 (fleet pull)

## Context
REQ-028 wants per-user daily/weekly trends and a funnel-evolution matrix in the
admin fleet view. That needs metrics **bucketed over time**, not the single
snapshot ADR-034 produces. Two ways to get history: accumulate snapshots forward,
or compute buckets from the raw tables — which already carry timestamps
(`events.ts_utc`, `applications.applied_at`/`created_at`, `viewed_jobs.viewed_at`).

## Decision
**Compute the time-series on demand from the raw tables.** Add
`core/bi/kpis.py::compute_kpi_timeseries(granularity, n)` returning per-bucket
funnel counts (active_days · viewed · saved · applied · tailored · heard_back).
The KPI CLI gains `--series`, which emits `{kpis, series_week, series_day}` in one
line so `fleet-pulse` gets snapshot + trends in a single SSH round-trip. Heard-back
timing comes from `app.status_changed` events (the transition moment); the rest
from durable tables.

## Alternatives considered
- Accumulate snapshots (the existing history JSONL): only builds forward, coarse,
  and can't show past weeks — fails the "see evolution" ask.
- A dedicated rollups table written on each event: write-path complexity + backfill
  pain for a handful of POC users.

## Consequences
Exact and retroactive (past weeks appear immediately), zero new storage, one KPI
source of truth so the trend can't disagree with the snapshot. Cost is per-bucket
queries at view time — negligible at POC row counts. Old-code apps that lack
`--series` fall back to snapshot-only in fleet-pulse (no drill-down until redeploy).
