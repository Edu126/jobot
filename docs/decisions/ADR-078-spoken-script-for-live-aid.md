# ADR-078: A separate cached call writes the live aid's spoken script

Date: 2026-10-12
Status: Accepted
Relates to: REQ-051, ADR-057, ADR-058, GOV-005

## Decision
P10 (`core/prep/spoken.py`) rewrites one answer frame into a 60–120-word
first-person script with spoken connectors, at `temperature=0`. It may only
add connectors; facts and numbers come verbatim from the frame, and unfilled
`[[hint]]` slots are dropped, never guessed. It runs at Practice start in
"With my answers" mode, in parallel, cached per (interview, question, lang,
PROMPT_VERSION + frame hash). Failure falls back to the frame's points.

## Why
Not a new toolkit field: that would bump the toolkit's PROMPT_VERSION and
regenerate every user's toolkit, and bloat a load-bearing call. A small
separate call only costs when someone practises with their answers, and a
changed frame naturally invalidates its script.
