# ADR-072: "Solid" needs the full story; only the number is optional

Date: 2026-10-07
Status: Accepted
Relates to: REQ-042 (#12, #13), ADR-059, EXP-002

## Context
A competency was "solid" at any 4 of the 5 checks. So "We cut approval time from ten days to three" counted as solid: it has a number, but the code gate removes `own_actions`. The rubric always said solid means "complete story, no number". The code never enforced that. EXP-002 measured 19% false-solid on a junk-answer set.

## Decision
`band_for` reads the checks instead of the point count:
- **strong:** all five checks
- **solid:** answered + example + own_actions + result
- **needs_work:** anything else

The 0–100 score still sums points.

## Alternatives considered
- Raise solid to 5/5: the number would become mandatory, too harsh for qualitative roles.
- Fix it only in the prompt: the model still drifts, and code is the stricter guard.

## Consequences
- False-solid fell from 19% to 8% (EXP-002). Controls still pass 100%.
- A competency can score 4/5 points and still band needs_work, which keeps the ready cap honest.
- Old sessions keep their stored bands.
