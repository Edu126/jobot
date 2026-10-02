# ADR-065: "With my answers" works in voice — the prepared answer follows the coach

Date: 2026-10-01 (backfilled same day)
Status: Accepted
Relates to: ADR-056/058 (answer cards), commit c09731c

## Context
Study mode was ignored by the voice runner. The cues were computed server-side and then dropped, because the model, not the app, controls which question is asked.

## Decision
- The live page tracks which question the coach is on. It matches the content-word stems of the *next* planned question against the coach's words (questions run in order), then shows that question's Get Ready script and point to land.
- The typed runner shows the same script.
- The modes are renamed "Help on screen": **No help** / **With my answers**. Stored values are unchanged (simulate/study).

## Alternatives considered
App-driven turns: that would undo ADR-052's direct-to-Live design.

## Consequences
Matching is a heuristic. If the coach rephrases heavily, the shown answer can lag one question.
