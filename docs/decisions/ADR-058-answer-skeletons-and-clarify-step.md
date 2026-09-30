# ADR-058: Answer skeletons with hint slots; Clarify step asks the HOW

Date: 2026-09-30
Status: Accepted
Refines: ADR-057 (one toolkit call) · ADR-056 (answer cards)

## Context
Eduardo's cards read vague: "How do you approach managing budgets?" got a paragraph
about a $25M budget and "strict financial oversight" — no approach. Root causes: one
prose format for every question type; prose invites filler when the résumé lacks the
method; we asked for new *facts* when the real gap is the *how*. His rule: don't invent
data — structure what's on the résumé and clarify the how.

## Decision
- **Skeletons, not prose.** Sections fixed in code per question type (approach:
  approach·example·result; behavioral: situation·action·result; opener: now·before·why_here;
  technical: what·how_i_used_it·example). ≤3 bullets, ≤14 words, first person.
- **Hint slots** `[[hint: …]]` where the inputs don't say how — rendered as dashed "fill
  in" chips; a code filler detector + hints mark the card `needs_input`.
- **Clarify step** opens Get Ready: 3–4 P1 questions about the how behind résumé items
  (example in the placeholder; Skip allowed). The Brief is read-only again.

## Consequences
Cards may show gaps instead of sounding complete — intended: gaps are honest prompts.

## Addendum — Story Bank in Profile + Strengthen (same day)
The how belongs to the story (account-level, reused by every interview). The Story Bank
moved to **Profile › Stories** (`/stories` redirects). `strength_check` gained
`missing_how` (short Action, no method connector). **Strengthen** asks one question per
flag (example in the placeholder; Get Ready's clarifications pre-fill the how) → one
`refine_story` call restructures the STAR with ONLY those answers → before/after preview →
saved on confirm. Editor/strengthen return to where the user came from (`?next=`).
