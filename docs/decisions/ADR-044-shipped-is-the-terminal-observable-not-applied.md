# ADR-044: "Shipped" (tailored + downloaded) is the terminal observable, not "applied"

Date: 2026-09-14
Status: Accepted
Relates to: REQ-026, ADR-034 (phase-0 KPIs), ADR-039 (leading signals), non-negotiable #1 (honesty)

## Context
The 2026-09-13 fleet pulse read **0 heard-back over 14 applications** and
`response_rate = null` across every app. The cause is structural, not seasonal:
**"applied" happens off-platform** (the user leaves Jobot for the company's ATS),
so we can neither observe it nor its response. Making it Gold #2 (G2) manufactured
a funnel that ends in a number we can't see. Meanwhile the strongest high-intent
action we *do* own is instrumented: downloading a tailored résumé. In the data,
that signal separates a real seeker (hermana: 64/70 downloaded) from a
tire-kicker (edu: 1/8). LinkedIn reached the same conclusion — surface an
intermediate "tailored/applied" status; don't overthink verifying the send.

## Decision
The **terminal observable event is `shipped` = a tailored résumé (or cover letter)
downloaded** — our owned analog of "applied". G2 becomes **résumés shipped / week**
(distinct downloaded jobs, this window vs prior). S3 (score trust) re-anchors from
applied jobs to **shipped** jobs. The leading funnel's terminal step is `shipped`,
not `applied`. **Outcome (heard-back) is demoted to an optional, self-declared
moat-seed with zero weight on the scorecard** — kept for the day a user volunteers
it, never a Gold metric, never a fake 0.

## Alternatives considered
- `tailored == applied` outright: rejected — inflates (edu tailors to try, never
  ships); download is the commitment signal that separates the two.
- Keep chasing real "applied"/response capture now: rejected — unobservable
  off-platform; nagging users for it costs trust for a number we can't trust.

## Consequences
KPI keys rename: `g2_applications`→`g2_shipped`, S3 `*_applied_*`→`*_shipped_*`,
funnel terminal `applied`→`shipped`. Consumers updated: `core/bi/kpis.py`,
`fleet-pulse`, `/admin/pulse`. Legacy `applied`/`heard_back` series columns stay
for back-compat. We stop measuring a phantom and start measuring the last thing we
actually see the user do.
