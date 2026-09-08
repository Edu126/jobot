# REQ-030: The BE SEEN · RANKED · REAL · SHINE narrative — future product page

Date: 2026-09-08
Source: Eduardo + team (emerged in the same meeting as REQ-029)
Status: Open (parked — do not build yet)

## What they asked for
"No intentaría meter 'Be seen · Be ranked · Stay real' aquí. Guárdalo. Porque
ahora veo que puede ser algo mucho más grande — la **arquitectura narrativa de
Jobot**." Mapped in the meeting:

- **BE SEEN** → résumé intelligence (ATS read + honest feedback)
- **BE RANKED** → job matching (real openings that fit)
- **STAY REAL** → tailoring (present your truth, nothing invented)
- **SHINE** → interview preparation (STAR from real experience)

## What they actually need
A place — a later **product/marketing page**, separate from the beta welcome
(REQ-029) — where Jobot's full story is told through this four-beat spine. This
is the home for everything REQ-029 deliberately cut: the 6-step journey timeline,
the gap-map / episodic→continuous hook, before/after tailoring demo, the "what
jobot refuses to do" pillars, FAQ, and the motto itself as the organizing frame.
The 6 cropped + palette-compressed screenshots in `ui_web/static/welcome/`
(01-upload … 07-gapmap) are the raw material — kept in the repo for exactly this.

Not for the first 10 beta users. This is for when there's cold acquisition
traffic to convince and the four product surfaces are mature enough to each carry
a beat.

## How we'll know it worked
A visitor who has never heard of Jobot can recount the four beats back
(see / rank / real / shine) and knows which product surface each maps to — the
motto stops being a tagline and becomes the mental model.

## Related
- REQ-029 (beta welcome — what this is explicitly NOT; keeps the welcome minimal).
- ADR-037 (the decision that parked this content and forbids re-accreting the
  welcome).
- Reuses archived copy/sections from git history + the welcome screenshots.
- Maps to the four product surfaces: résumé/ATS (REQ-021), matching/scoring
  (REQ-015), tailoring, and Prep (REQ-023).
