# ADR-057: One toolkit call after the Brief; the Brief asks for missing facts

Date: 2026-09-30
Status: Accepted
Supersedes: the P2 ∥ P3 → P4 chain of ADR-048 / ADR-056 (the answer cards themselves stay)

## Context
Get Ready showed "Building this part…" per tab: three calls (questions, story mapping,
answers) re-sent the same brief + résumé, each seeing a slice. Answers read vague
because the résumé is vague. Eduardo: build it once, from the brief; ask me first.

## Decision
- **P1 Brief** also writes 3–4 `fact_questions` — specifics the résumé doesn't state.
  The Brief's one CTA submits the (optional) answers (`prep_artifacts` kind `facts`).
- **One toolkit call** (`core/prep/toolkit.py`) with brief + fact answers + Story Bank
  + résumé writes: likely questions with first-person answers, one story per competency
  (bank pick or a STAR draft to save), questions to ask (why + what it shows).
- Get Ready renders all three tabs from that one artifact; one loading state.

## Consequences
2 calls per interview instead of 4. Editing a story or a fact answer regenerates the
whole toolkit (bigger, rarer). A mega-call with the Brief was rejected: the Brief would
appear later and the facts couldn't feed the answers.
