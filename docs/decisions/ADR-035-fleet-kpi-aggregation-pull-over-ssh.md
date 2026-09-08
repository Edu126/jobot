# ADR-035: Fleet KPI aggregation is a local pull over SSH — no central store

Date: 2026-09-08
Status: Accepted
Relates to: REQ-026, ADR-001 (app-per-user), ADR-034 (deterministic KPIs),
non-negotiable #3 (data isolation), non-goal "no third-party telemetry"

## Context
Each user is a separate Fly app with its own SQLite volume (ADR-001), so KPIs
live in N isolated DBs. Reading them means opening `/admin/pulse` per app — no
fleet view. We want one aggregated dashboard (rollup + per-user table + trend)
without standing up infra or weakening isolation, on a solo-maintainer POC budget.

## Decision
A **local, owner-run pull**: a `fleet-pulse` skill iterates the apps, runs
`fly ssh console -a <app> -C "python -m core.bi.kpis"` (which prints the
deterministic KPI JSON from ADR-034), and renders a single local HTML dashboard
(rollup cards + detailed table + inline-SVG activity sparklines from
`g1.weekly_active`). Each run appends a rollup line to a local history JSONL so
trend lines build over time. Only **aggregate numbers** leave each app, pulled by
the owner over authenticated SSH.

## Alternatives considered
- Push to a central store/DB: new infra + raw-ish data leaving the app = weakens
  isolation and trips the "no third-party telemetry" non-goal.
- Central aggregator app: over-engineered for a handful of POC users.
- Keep per-app pulse only: no fleet read — the whole ask.

## Consequences
Snapshot-on-demand (you run it), not always-live — fine at POC scale. Reuses the
one deterministic KPI function, so the fleet view can never disagree with a single
app's `/admin/pulse`. App→user labels are maintained by hand in the skill and
**must be verified** (names don't match users). Revisit at multi-tenant exit,
where a shared DB makes a real dashboard trivial.
