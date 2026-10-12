# ADR-081: The session score has three pillars: Content, Structure, Delivery

Date: 2026-10-12
Status: Accepted (not built yet)
Relates to: REQ-042, REQ-043, REQ-052, ADR-059

## Decision
The 0–100 session score becomes three scored pillars:
- **Content (≈50%)**: what you said. Answers the question, a real situation,
  your own actions, a result tied to them, why it mattered, the link to the
  role. Judged by the REQ-052 evaluator, measured against Eduardo's labels.
- **Structure (≈25%)**: how it's organized. Answer first, situation → action →
  result, one clear message, 1–2 minutes. The model gives evidence, code
  does the maths.
- **Delivery (≈25%)**: how it sounded. Pace, fillers, pauses, measured in code.
A session can't be "ready" while Content is weak, however good the delivery.

## Why
Today's 5 checks only test that pieces are present, so disconnected answers
scored 95 (session 55). Eduardo: "it's important to evaluate the way to say
things but also what is said." Weights get tuned on the reference set.
