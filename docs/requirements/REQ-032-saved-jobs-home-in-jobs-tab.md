# REQ-032: Saved jobs get a home in the Jobs tab

Date: 2026-09-08
Source: Eduardo (reading the fleet-pulse funnel — `saved` ~0 everywhere)
Status: Open

## What they asked for
Verbatim: "una vez le das saved, este no se guarda o no se ve en ningún lado …
cuando la gente le da saved, podemos mostrar esos en el job tab, tipo saved jobs?"

## What they actually need
Saving **does** persist — the ❤️ creates an `interested` application
(`partials/save_action.html`, `jobs.py:2127` `JOB_SAVED`). But it only surfaces in
the Applications/Journey tab; in the **Jobs** tab the heart just turns red and
nothing else happens. No payoff → nobody saves → `saved` is ~0 fleet-wide (only
the power user, who found Applications, saves).

Give saved jobs a home **inside the Jobs tab**:
- A lightweight "Guardados / Saved" filter or section that lists the user's
  `interested` jobs, reusing the existing query + `job_card.html` render.
- No new data model. No new card fields (respect card-density feedback). Missing
  data degrades gracefully.

## How we'll know it worked
After tapping ❤️, the job shows up under a "Guardados" view in the Jobs tab
without leaving the tab; the `saved` line in the funnel starts moving.
