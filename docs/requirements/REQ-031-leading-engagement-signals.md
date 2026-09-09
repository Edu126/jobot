# REQ-031: Leading engagement signals — reframe the funnel around what users actually do

Date: 2026-09-08
Source: Eduardo (reading the fleet-pulse funnel)
Status: Open

## What they asked for
Verbatim: "los usuarios rara vez van a decirnos que aplicaron, por eso, buscar,
save, tailor, profile gap viewed, y prep son nuestras señales iniciales."

## What they actually need
The funnel-evolution matrix (REQ-028) ends `viewed → saved → applied → tailored →
heard_back`, leaning on `applied`/`heard_back` — both **self-reported** and ~0
fleet-wide (`kpis.py` `_HEARD_BACK`, `applications.applied_at`). That reads as
failure when it's really *unreported*. The signals we can trust are **first-party
and already logged**: search (`search.*`), save (`job.saved`), tailor
(`tailor.generated`), prep (`prep_session_created`), and **profile-gap viewed —
which has NO event yet and must be added** (`events.PROFILE_GAP_VIEWED`, tracked
where the aggregated gap map renders).

Rework the activation/engagement view around these leading signals:
- Update `FUNNEL_STEPS` + `_bucket` in `core/bi/kpis.py` so the per-bucket series
  counts search · save · tailor · gap-viewed · prep (reading `events` by type).
- Update the fleet-pulse matrix columns to match.
- Keep `applied`/`heard_back` as a **trailing outcome**, not the activation gate.
- Additive/back-compatible: apps on old code (no new event) render 0, never break.

## How we'll know it worked
The fleet-pulse funnel shows search → save → tailor → gap → prep per week; a user
who searches + tailors reads as *engaged* even with 0 applied.
