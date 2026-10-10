# ADR-074: Acknowledge by restating a detail; wait 2.5 s before taking the turn

Date: 2026-10-08
Status: Accepted. Supersedes the "mhm / right / got it" and filler rules of the ADR-069 voice direction.
Relates to: REQ-048, REQ-044, ADR-069

## Context
Two prompts told the coach to answer with listener sounds:
- `NATURAL_SPEECH`, the lab-winning voice direction, said "mhm", "right", "got it", "hmm", "um".
- The P7 interviewer prompt said "a short listener cue is often enough (Mm-hmm…)".

In real sessions a bare "Mm-hmm" sounded inattentive. Separately, VAD `silence_duration_ms = 700` handed the turn to the coach whenever the candidate paused to think.

## Decision
- **One source for acknowledgments: P7.** The coach restates one concrete detail without judging it ("Thanks — so you ran the vendor review yourself."). Fallback: "Okay, thank you." Never a bare listener sound. `NATURAL_SPEECH` now covers only the sound of the voice (no filler sounds, short turns). P7 version bumped; the core prompt is 2,429 chars, still under the 2,500 budget.
- **Pause: `live.SILENCE_MS = 2500`.** This is the one constant for production and the lab default. The lab slider now reaches 5 s for testing.

## Alternatives considered
- 5 s pause, as asked: no cut-offs, but 5 s of dead air after every answer feels like a dropped call. Eduardo chose 2.5 s.
- Fix it only in `NATURAL_SPEECH`: P7 would still allow "Mm-hmm".

## Consequences
- Each turn takes about 1.8 s longer.
- Restating a detail relies on the model getting the detail right. A wrong restatement would be worse than "Okay". Watch for it in the next sessions.

**Update 2026-10-10 (session 46 on -edu):** acks were accurate and no answer was
cut off at 2.5 s, but all 5 opened "Thanks — so you…" — the model copied the
single example. Now: three differently-shaped examples + "never start two
acknowledgments the same way" (P7 `2026-10-10-interviewer-v3-varied-acks`).
