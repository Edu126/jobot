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
