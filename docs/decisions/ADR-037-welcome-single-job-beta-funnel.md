# ADR-037: The welcome page is a single-job beta funnel, not a product explainer

Date: 2026-09-08
Status: Accepted
Relates to: REQ-029 (supersedes REQ-027's timeline execution)

## Context
The welcome page had accreted into a full product explainer: a 6-step journey
timeline (REQ-027), plus a conversion layer bolted on the same day (ATS banner,
before/after toggle, floating badges, sticky header, FAQ, "refuses to do" cards,
a motto band). Five-plus messages competed for attention. But the real audience
right now is **~10 beta users Eduardo mostly knows** — not cold acquisition
traffic. The page's job is comprehension + one click, and everything past that
was cost, not value. A team meeting produced the criterion: *"Its only job is —
I understand what Jobot is, I'm curious, I want to click Start."*

Tension weighed live: the page had just been built and iterated (sunk effort),
and an invented "+22%" / bouncing "88%" style would have boosted a conversion
page — but conversion isn't the goal, and fabricated stats fight the brand's
honesty (non-negotiable).

## Decision
Strip the welcome to a single-job funnel: header → hero (eyebrow + headline +
one Find/Tell/Shine sentence + CTA + screenshot) → 3 cards (match/tailor/prepare)
→ philosophy line + closing CTA → founder note → footer. No nav, no timeline, no
FAQ, no interactive gimmicks. Everything else is **archived (not deleted)** for a
later product/marketing page. The founder note is kept deliberately: for a beta
cohort it is the highest-value element (sets expectation, invites "tell me where
it breaks").

## Alternatives considered
- **Keep the full explainer** — richer, but diluted the one job and carried a
  maintenance surface no beta needs.
- **Add conversion tactics (fake metrics, bounce)** — would lift a marketing
  page, but we're not converting cold traffic and it breaks honesty.
- **Delete the archived sections outright** — loses reusable, already-built copy
  and 6 cropped/compressed screenshots the future product page will want.

## Consequences
The page now converts to *comprehension + click* for people who already trust
Eduardo — deliberately weak for cold SEO/acquisition traffic (accepted; that's a
later page's job). Repetition between the hero sentence and the 3 cards is kept
on purpose (promise→proof aids first-time comprehension). We now owe a separate
product page later, and must not let the welcome re-accrete features — new
product-explaining content goes to REQ-030's page, not here. Superseded content
lives in git history + the archived screenshots.
