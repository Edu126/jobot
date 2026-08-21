# REQ-003: AI resume summary must be grounded in the resume

Date: 2026-08-20
Source: User, triggered by a real hallucination in Sara's cached
summary ("Big multinational brands here, but the sudden pivot to
art gallery work feels totally random and unconvincing" — for a
resume with zero art or gallery content)
Status: Shipped (ADR-005, hardened prompt + Pydantic grounding
validator + silent single retry)

## What they asked for

> "something about saras resume statement, it says 'the sudden
> pivot to art gallery work feels totally random and unconvincing.'
> i dont see anything about art galleries on her resume."

Then, when the initial fix (a user-facing Regenerate button) shipped:

> "a regenerate btn... should be something we get from other
> prompts, using pydantic to get the data. porque estamos abriendo
> espacios donde el usuario puede regenerar tantas veces que se
> vuelve peligroso"

And generalized:

> "no es solo el regenerate btn, it should be about making systems
> more simple, not adding complexities."

## What they actually need

The ask reads as "fix Sara's summary." The actual need is deeper:
a **system-wide guarantee** that any AI-generated text shown to a
user is either grounded in the source or doesn't render at all.
This is not one summary's problem — it's the design pattern for
every current and future AI surface (scoring reasoning, cover
letters, quick-fill suggestions, pulse report, anything downstream).

The user pushback also crystallized a principle: **quality lives in
the contract layer, not in user-facing escape hatches.** That
principle became ADR-005 and is now a non-negotiable in the
architecture vision (#2).

## How we'll know it worked

- Users stop reporting AI-invented biographical details ("I never
  did X," "this isn't my background").
- No user-facing "Regenerate / Retry" buttons appear on AI outputs
  going forward.
- `tests/test_ai_summary_grounding.py` passes; new AI surfaces get
  equivalent test coverage.
- When a summary can't be grounded, no summary renders (deliberate
  silence, not a warning banner).

## Related

- ADR-005 (Quality-in-contracts, not user-facing escape hatches).
- Vision non-negotiable #2.
- `ui_web/routes/profile.py:_grounded_or_none` (the pattern).
- `tests/test_ai_summary_grounding.py` (9 fixtures locking the
  invariant).
- Memory: `feedback_simplicity_over_escape_hatches.md`.
