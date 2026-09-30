# ADR-056: Answer cards replace flashcards + talking points; Get Ready = 2 tabs

Date: 2026-09-30
Status: Accepted
Relates to: ADR-048, REQ-041, GOV-005

## Context
Eduardo on the live Get Ready: P4 flashcards were third-person study trivia ("How has
Eduardo demonstrated…") whose backs echoed the Brief (§2A.3). Four tabs overlapped:
flashcards, likely questions and talking points were three views of "what to say".

## Decision
- **P4 answers the P2 questions** in the candidate's first person, 2–4 sentences, built on
  the P3-mapped story; each answer carries a `point_to_land` (absorbs talking points).
  Runs after P2 ∥ P3; cache version folds brief + questions + mapping fingerprints.
- **Get Ready = Answer cards · Your stories.** Questions-to-ask stays, read-only, under the deck.
- **Self-rating** (`card_reviews`, append-only, latest wins, text-guarded) — "missed" cards
  lead the next Practice session (`pick_session_questions(prefer_ids=…)`).

## Consequences
One P4 call per interview still; P4 now waits for P2/P3 (background, invisible). First
self-reported learning signal we store.
