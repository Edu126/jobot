# REQ-006: Finish AEC debias in search / matching / seeds

Date: 2026-08-21
Source: User (follow-up to REQ-005 during ADR-007 review)
Status: Building (implemented 2026-08-26, pending PR review)

## What they asked for

> "b" — file a follow-up for search-side cleanup.

Scope: the AEC assumptions that live *outside* the evaluation prompts
covered by ADR-007. Concrete files:

- `core/matching/tfidf_match.py:21-23` — "Domain-aware extras for
  AEC/construction roles the user is targeting" (AEC tooling weights
  that generic English stopword lists ignore).
- `core/jobs/saved_searches.py:3` — "Tuned for the AEC/construction
  roles user's boyfriend is targeting."
- `core/db.py:333` — comment on seed defaults that used to be AEC.
- `core/resume/section_presence.py:73-76` — AEC-first tools list.
- Any residual AEC framing in comments/tests that isn't an explicit
  AEC fixture.

## What they actually need

The scoring debias (ADR-007) is only half the win — a Sales candidate
whose scoring prompt is now neutral will still see AEC-tuned TF-IDF
matches, AEC-tuned saved-search chips, and AEC-first stopword extras.
That's the same underlying bug (single-user assumptions leaking past
their layer) surfacing in ranking / recommendation / defaults instead
of scoring. This REQ finishes what REQ-005 started so the grep success
criterion in REQ-005 (`grep -ri aec ...` returns only labelled test
fixtures) actually holds.

## How we'll know it worked

- `grep -rniE 'aec|architect.{0,20}(engineer|construct)' core/ ui_web/`
  returns only test fixtures explicitly labelled AEC, or generic
  vocabulary lists where AEC terms sit alongside terms from other
  domains as peers.
- A Sales / BI / tech user sees ranking + saved-search defaults that
  aren't skewed toward AEC vocabulary.
- No user-visible copy references AEC unless the user's own resume
  places them in AEC.

## Related

- REQ-005 (parent — this is the second slice).
- ADR-007 (scoping decision that carved this out).
- ADR-TBD: likely one small ADR on "domain vocabulary as data, not
  code" if the fix ends up moving the term lists into config /
  candidate-derived signal.
