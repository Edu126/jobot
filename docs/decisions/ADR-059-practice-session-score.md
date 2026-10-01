# ADR-059: Practice sessions get a rubric-built 0–100 score

Date: 2026-10-01
Status: Accepted
Relates to: REQ-042, REQ-041. Partially supersedes ADR-048 "bands not scores", for Practice only.

## Context
The voice debrief asked Gemini for one holistic band per competency from the WAV. There was no rubric, no evidence and no "not covered" option, and it rated junk answers "Solid". Its delivery numbers (305 wpm) were model guesses. Eduardo wants a score per session.

## Decision
The LLM answers 5 yes/no checks per competency and quotes the candidate's words. Code then:
- verifies the quote against the transcript
- applies the number and first-person gates
- sums the points into a 0–100 score
- derives the bands and the verdict

Not-asked competencies are excluded from the score. Delivery is counted in code.

## Alternatives considered
- Holistic LLM 0–100: drifts and flatters.
- A hiring verdict only: can't show small progress.
- Out of 10: reads more generous than it is.

## Consequences
One extra JSON block per debrief, and no migration. Legacy sessions render bands without a score. The model can still be lenient about real-but-weak quotes, so the quote is shown next to each tick.
