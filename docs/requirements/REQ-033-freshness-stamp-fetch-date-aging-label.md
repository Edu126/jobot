# REQ-033: Freshness — stamp the fetch date, let the recency label age

Date: 2026-09-08
Source: Eduardo
Status: Open

## What they asked for
Verbatim: "si hoy hacemos extracción, a veces la data viene con ?? y lo cambiamos
a <24h, eso no puede quedar muerto; si la persona abre eso mañana, eso se debería
actualizar … o por defecto ya dejar la fecha del día actual so no nos estresamos."

## What they actually need
`partials/job_card.html:56` renders `jobs.date_recent` ("≤24h" / "hoy") whenever
`date_posted` is empty for a LinkedIn job. That label **encodes no timestamp** —
it never ages, so a job fetched 5 days ago still says "hoy". A lie that gets worse
with time.

Fix in the **ingestion / contract layer, not the view** (per the "fix quality in
the contract layer" principle):
- When `date_posted` is empty, default it to the **fetch date** — mirror what
  `core/jobs/ats/base.py:138` already does (`… or date.today().isoformat()`); the
  jobspy / `_coerce_date` path in `core/jobs/search.py` currently leaves it empty.
- Then `humanize` / the card label computes real recency and ages on its own; the
  frozen "≤24h" branch can retire (or only ever show for a genuinely same-day fetch).

## How we'll know it worked
A job with no publisher date shows today's date on ingest, and on reopening days
later reads "3d ago" / its real date — never a frozen "≤24h".
