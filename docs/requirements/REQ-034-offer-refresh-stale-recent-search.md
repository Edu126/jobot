# REQ-034: Offer to refresh a stale recent search

Date: 2026-09-08
Source: Eduardo
Status: Open

## What they asked for
Verbatim: "shall we ask when a recent job search is open to 'refresh the view for
you, so you get the latest job' — this is trigger if the data is fetched more than
2 days ago?"

## What they actually need
Recent searches carry `fetched_at` (`core/jobs/cache.py`). Reopening one whose
data is days old shows listings that may be dead — the results "ya no valen la
pena". Add a **one-tap inline offer** (banner on the results page) when
`now - fetched_at > 2 days`: "Actualizar para traer lo último / Refresh for the
latest jobs."

Constraints:
- **Offer, not auto.** A refresh hits jobspy / Photon (rate limits + cost). Never
  fire it on open.
- Reuse the existing `POST /jobs/refresh/{key}` endpoint (`jobs.py:1764`).
- Fresh searches (≤2 days) show no nudge — no noise.

## How we'll know it worked
Opening a 3-day-old search shows the refresh nudge; a fresh one doesn't; tapping
it re-runs through the existing refresh path and updates the view.
