# ADR-071: Voice answers are split where the coach's turns start

Date: 2026-10-06
Status: Accepted
Relates to: REQ-043, REQ-042, ADR-070

## Context
The answer-length gauge needs seconds per answer. Typed practice has them. Voice only had one session total, so the gauge never appeared.

## Decision
- The browser records the sample offset in the candidate audio whenever a coach turn starts, and uploads these offsets with the WAV.
- The server cuts the audio at those offsets and measures each piece with ADR-070's speaking clock. The noise floor is computed once over the whole recording.
- Pieces under 8 s are dropped as replies, not answers ("yes, ready").
- The gauge shows the average of the answers that are left.

## Alternatives considered
- Split on transcript turns: no timing data, and the transcript arrives in bursts.
- Ask the model to segment: violates REQ-042.

## Consequences
- A coach backchannel ("mm-hm") mid-answer splits that answer in two. The P7 prompt already tells the coach not to interrupt.
- Answers under 8 s are invisible to the gauge.
- Sessions before this change show no length gauge.
