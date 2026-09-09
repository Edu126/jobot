# ADR-039: Leading signals report intention (default) and intensity (toggle)

Date: 2026-09-08
Status: Accepted
Relates to: REQ-031, ADR-036 (on-demand time-series)

## Context
REQ-031 reframes the funnel around leading first-party signals (search · save ·
tailor · gap-viewed · prep). The first cut counted **raw events**: 8 job searches
in one day = 8; switching the gap-map lens all→top3 = 2 gap_viewed. That inflates
for multi-query sessions and conflates "did they engage?" with "how hard did they
push?" — two different questions the fleet view must not blur.

## Decision
Compute **both** measures per signal, per bucket, in `core/bi/kpis.py::_bucket`:
- **Intention** — distinct active days the user did the thing at all
  (`<signal>_days`, `COUNT(DISTINCT day)`). The honest "engaged this week?" line.
- **Intensity** — raw event count (`<signal>`). How much they pushed.

`fleet-pulse` renders **intention by default**; a single toggle button flips every
matrix cell to intensity (each `.lead` cell carries `data-days` + `data-raw`).
Distinct-days is always ≤ raw (asserted in tests).

## Alternatives considered
- Raw only: simple, but inflates and answers the wrong question for a 6-user beta.
- Distinct-days only: honest engagement, but loses the intensity signal (a power
  user tailoring 15× reads identically to one tailoring once).

## Consequences
Two additive keys per leading signal; old apps lacking `_days` fall back to the raw
value (render cleanly, can't distinguish modes until redeployed). Negligible extra
queries at POC scale. `prep_session_created` is still a string literal, not an
`events` constant — promotion deferred, noted in REQ-031.
