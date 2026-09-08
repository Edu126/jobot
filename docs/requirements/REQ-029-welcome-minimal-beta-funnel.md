# REQ-029: Welcome page — minimal beta funnel (supersedes REQ-027's timeline)

Date: 2026-09-08
Source: Eduardo + team (post-meeting call, relayed same day)
Status: Shipped (on -edu; awaiting fan-out)

## What they asked for
"Esta no es la página para explicar todo Jobot. Es la welcome page para los
primeros 10 beta users. Su único trabajo es: *'I understand what Jobot is, I'm
curious, and I want to click Start.'* Todo lo demás puede venir después. Yo la
simplificaría bastante."

The prior build (REQ-027 timeline + a conversion layer added on top: 6-step
journey, gap-map section, before/after toggle, floating badges, sticky header,
FAQ, "refuses to do" cards, motto band) had grown into a full product explainer —
5+ messages competing for attention.

## What they actually need
A single-screen-ish funnel whose ONE job is comprehension + click, for a known
cohort of ~10 beta users. Not a marketing site, not an explainer. The final
shape:
- **Header:** Jobot + language toggle. No nav (there's only one path: Start).
- **Hero:** small eyebrow ("Enterprise-level hiring intelligence, built for you"
  — enterprise intent without stealing focus) → "You do the heavy lifting. / We
  make it lighter." → one sentence with Find/Tell/Shine rhythm ("Find the job
  that matches your strengths. Tell your story your way. Walk into the interview
  ready to shine.") → **Start now →** (`/profile`) → product screenshot beside.
- **3 cards** (MATCH → TAILOR → PREPARE): Find your fit · Tell your story ·
  Prepare to shine. Deliberate promise→proof echo of the hero sentence: repetition
  aids the exact comprehension goal for a first-time visitor.
- **Philosophy block** (finally with context): "Nothing invented. No fluff. Just
  you, presented better." + a **closing CTA** (a visitor who scrolled shouldn't
  have to scroll back).
- **Founder note** (kept past the team's "STOP" — for these 10 users it's the
  highest-value block: sets beta expectation, invites "tell me where it breaks").
- Footer: privacy line + Jobot · 2026.

Constraints carried from REQ-027: hero/guide voice (ADR-032), web-first
(ADR-033), bilingual EN/ES, honest (no invented metrics, no fake social proof),
house Phosphor icons only (no emoji), CTA → `/profile`.

Archived for a later product/marketing page (NOT deleted): the 6-step timeline,
gap-map section, before/after, badges, FAQ, "refuses to do", and the
Be seen·ranked·real motto (see REQ-030). The 6 cropped+compressed screenshots
stay in the repo to feed that page.

## How we'll know it worked
A beta user opens the page, in one scroll understands "this helps me find where I
fit, present myself better, and prepare," and clicks Start — without a hand-hold.
S1 activation is measured in-app (REQ-026), not here.

## Related
- **Supersedes** REQ-027's "real product journey timeline" content direction
  (the present/manual/hand-off *intent* still holds; the explainer *execution*
  was too much for a 10-user beta).
- ADR-037 (welcome = single-job beta funnel — the decision behind this).
- ADR-032 (hero/guide voice), ADR-033 (web-first).
- REQ-030 (the archived narrative architecture for the future product page).
