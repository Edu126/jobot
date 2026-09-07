# REQ-027: The stranger one-pager — present · manual · hand-off (not onboarding)

Date: 2026-09-07
Source: Eduardo (strategy session — "landing one pager para esos strangers")
Status: Open

## What they asked for
"Estamos construyendo el landing one-pager para esos strangers… ahí va a estar
todo lo que necesita presentarles para el onboard." A reusable presentation-layer
artifact for the Phase 0 stranger cohort: screen captures, works to present the
product, and a "how to use" manual — oriented mainly for the instrumentation
stage, but reusable later as the public landing page.

## What they actually need
One scrollable page that does the jobs a static page *can* do — **present,
convince, orient, manual, and hand off into the app** — without pretending to be
the onboarding itself. Adversarial split (locked in review): the **page** presents
and manuals; the **app** onboards, activates, and instruments. The page's only
onboarding job is a strong "start here" link into the app; activation (S1) is
measured in-app, not here.

Constraints:
- **Voice: user is the hero, jobot the guide** (ADR-032). "La estrella eres tú;
  somos tu equipo de soporte." Never "we do it for you."
- **Web-first** (ADR-033): wide desktop workspace, denser reading; mobile is
  graceful degradation. Prep is the mobile exception.
- **Honest social proof:** we have none — do not fake it. A founder's note
  ("built with 4 people, you're one of the first 10, tell me where it breaks")
  beats invented testimonials (non-negotiable #1).
- **Carnita only:** hero (StoryBrand SB7) → 3-step plan → 3 REAL screenshots
  (pulled from -edu) → manual (accordions, reuse REQ-025 kit) → one CTA into the
  app → founder's note. No nav, no pricing, no blog. If it can't be pasted into a
  DM, it's too big.
- LatAm Spanish register primary (REQ-001), English parallel.

On the side (companion artifacts, tracked here): the **intake form** (<5 fields:
actively hunting? · biggest pain · check-in contact · consent-to-instrument),
the **30-sec recruit pitch**, and the **Mom Test** interview script.

## How we'll know it worked
A stranger who has never met Eduardo reads the page, understands what jobot is
(and what it refuses to do), and clicks into the app to try it on a real job —
without a hand-hold. Where they silently stall = the onboarding bug list, for free.

## Related
- ADR-032 (hero/guide voice — blocks the copy), ADR-033 (web-first).
- Feeds REQ-026 S1 activation (top-of-funnel); does not block REQ-026 metrics.
- Screenshots via the verify-on-edu skill (real product, not mockups).
- Design rules: CRAP + skeleton loaders (standing UI conventions).
