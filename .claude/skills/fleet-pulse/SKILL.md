---
name: fleet-pulse
description: Aggregate all Jobot users' Phase 0 KPIs into ONE local dashboard. Use when the user wants a fleet-wide view of retention/activation/applications across every Fly app (instead of opening /admin/pulse per user) — triggers like "vista agregada", "dashboard de todos los usuarios", "cómo van todos", "fleet pulse".
---

# fleet-pulse — one dashboard for the whole fleet

Each user is a separate Fly app with its own SQLite (ADR-001), so KPIs are in N
isolated DBs. This skill pulls the **deterministic Phase 0 KPIs** (ADR-034) from
every app over SSH and renders **one local HTML dashboard** — rollup cards, a
detailed per-user table, and activity sparklines. Owner-run, pull-only; only
aggregate numbers leave each app (ADR-035, respects data isolation).

## Run it

```bash
python3 .claude/skills/fleet-pulse/fleet_pulse.py
```

- Discovers `jobbotv2*` apps via `fly apps list --json` (or pass app names as args).
- For each app runs `fly ssh console -a <app> -C "python -m core.bi.kpis"` — the
  KPI CLI prints one JSON line; the script parses it. Wakes stopped machines;
  budget ~10–20s per app.
- Writes `/tmp/fleet_pulse.html` (open it) and appends a rollup to
  `~/.jobot/fleet_pulse_history.jsonl` so the "users active" trend line grows
  across runs.

## What it shows

- **Rollup cards:** users active this week · W1 / W4 retained · activated ·
  applications this week · heard-back / applied.
- **Table (row per user):** active · W1 · W4 · apps/wk (Δ) · activated · accept% ·
  avg applied score · response% · activity sparkline (from `g1.weekly_active`).
- **Trend:** users-active-this-week across historical runs.
- **Per-user drill-down (REQ-028):** a filterable list of `<details>`, each with a
  **funnel-evolution matrix** (rows = weeks, cols = viewed → saved → applied →
  tailored → heard) + **weekly-applied** and **daily-activity** sparklines. Pulled
  via `python -m core.bi.kpis --series` (ADR-036); apps whose code predates
  `--series` still show the table row but no drill-down (redeploy them).

## Guardrails

- **Read-only.** No seeding, no writes to any app — no backup/restore needed
  (unlike `verify-on-edu`). It only runs the KPI CLI, which is pure reads.
- **Labels lie.** App→user names DO NOT match (memory
  `reference_fly_app_user_mapping`). The `LABELS` dict in `fleet_pulse.py` is
  hand-maintained and marked "(verify)" — confirm before naming a user anywhere.
- Requires `fly` authed as the owner. An unreachable app renders as
  "unreachable", never a fake 0.
- Needs each app deployed with the KPI CLI (`python -m core.bi.kpis`, ADR-034+).
  If an app predates it, redeploy that app first.
