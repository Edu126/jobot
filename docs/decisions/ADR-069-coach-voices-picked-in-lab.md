# ADR-069: Coach voices and delivery are the voice-lab winners

Date: 2026-10-02
Status: Accepted. Supersedes the 5-voice set of ADR-063 (the decoupling still stands).
Relates to: REQ-044, REQ-046, ADR-068

## Context
Eduardo tested takes on the real Live model in the voice lab (ADR-068) and picked three by ear. All three were "opening" mode, slower and calm, with the default pause stretch (0.18 → 0.6 s) and his own voice direction.

## Decision
- The coach voices become:
  - **Erinome → Anna** (default), medium energy
  - **Sulafat → Maya**, high energy
  - **Iapetus → Tom**, medium energy

  All three are slower and calm. The names are short and friendly, and never a real user's name.
- `live.VOICE_DELIVERY` holds each voice's preset. `live.NATURAL_SPEECH` holds his voice direction: short acknowledgments, at most one light filler per turn, an occasional self-correction, short turns. Together they become P7's Delivery line for every real session.
- One edit to his rule: "use acknowledgments *while* the candidate answers" became "*when* they finish a point". Live would otherwise talk over the candidate.
- The voice previews were regenerated from Live with each preset.

## Alternatives considered
Keeping 5 voices: they were chosen on paper, before the lab existed.

## Consequences
P7 grows to about 3,400 chars. That's fine: no hang up to 20k (ADR-053 update). Old sessions that stored a retired voice fall back to the default.
