# ADR-077: A topics checklist replaces length + focus; code orders the arc

Date: 2026-10-10
Status: Accepted. Supersedes ADR-076's length-based character slots (the bank and rotation stand).
Relates to: REQ-050, ADR-076, ADR-056, ADR-059

## Decision
Setup is one checklist: "About you" + each competency, all checked (Feedback's
"Drill" link checks only that one). A session = one opener + one question per
checked item, so the count is visible and coverage grows with what's checked.
Code orders the arc: career (opener) → about you (character bank) → the role
(approach → behavioral → technical → situational). Each question is tagged by
part in the context turn and the coach bridges between parts with one
sentence. Per topic, a missed answer card wins, else the least recently asked.
The Feedback step always links: latest session, past sessions listed, or an
empty state.

## Why
Two controls (length, focus) become one that also explains what's evaluated
(§2A subtract-first). Code-owned order keeps the arc the same every time.

**Update 2026-10-10 — live aids:** Eduardo picked glanceable talking points
(option a) over keywords. The live page now shows the prepared answer as one
large line per point, no STAR labels, point to land last
(`partials/live_talking_points.html`); the question itself is small and muted.
Code-only — same frame data, no regeneration.
