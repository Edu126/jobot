# ADR-066: The coach (P7) behaviour contract

Date: 2026-09-28 → 2026-10-01 (backfilled)
Status: Accepted
Relates to: REQ-044, ADR-053 (split prompt), commits c9ddff9, 621a77f

## Context
Live QA problems:
- the coach repeated "the {role} at {company}" every turn
- it restarted its greeting when the candidate went off-topic
- it sounded salesy
- it opened inconsistently

## Decision
The pinned P7 prompt sets these rules:
- Opening: "Hello {first name}, I'm {coach}. Thanks for making the time today — we'll talk about the {role} role at {company}."
- Name the role and company only in that greeting.
- One follow-up at most per question.
- When the candidate goes off-track, briefly name it and go to the next question. Never restart.
- A calm HR register: no hype, no praise.
- A fixed closing line ("That concludes our practice interview.").

The prompt stays **< 2500 chars**. Tests enforce this, because of the Live silent hang near ~4000.

## Alternatives considered
App-side turn control: rejected, see ADR-052.

## Consequences
Every rule competes for the character budget. New behaviour must replace text, not add to it.

## Update 2026-10-02 — the ~4000-char hang no longer reproduces
Measured on `gemini-3.8-live`: system prompts of 2,500 / 4,000 / 6,000 / 10,000 / 20,000 chars all answered in 3–4 s, both on a direct connection and through an ephemeral token with the prompt pinned (the coach's path). The limit was either the previous model or a different cause. We keep the base coach prompt < 2,500 chars as a **focus budget** (shorter instructions are followed better), not as a hard ceiling. The voice lab now allows a 1,500-char extra instruction.
