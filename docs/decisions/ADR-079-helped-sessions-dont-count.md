# ADR-079: Sessions with your answers on screen are labelled and don't count

Date: 2026-10-12
Status: Accepted
Relates to: REQ-042, REQ-051, ADR-059

## Decision
A "With my answers" (mode `study`) session still gets its score, but Feedback
labels it "With help" and says why; Past sessions mark it too. Its score is
compared only with other helped sessions, and it never feeds Readiness (not
the "practised once" count, not the latest competency bands).

## Why
Session 55 scored 95 while Eduardo read the spoken scripts aloud. Reading your
own prepared answer proves the answer is good, not that you can say it
unaided; counting it would inflate Readiness — the opposite of "strict by
default" (REQ-042). Eduardo chose this over a separate score or no change.
