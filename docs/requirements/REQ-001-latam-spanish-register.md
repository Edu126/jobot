# REQ-001: LatAm Spanish register, not Spain

Date: 2026-08-20
Source: User (also observable in Sara's + Melissa's usage — all
Spanish-speaking beta users are LatAm-based, none in Spain)
Status: Shipped (PR A, 2026-08-20)

## What they asked for

> "we need more a latin american spanish, so its easier to read"

## What they actually need

Every ES-generating surface — LLM prompts, template strings, error
messages — defaults to Latin American register. **"Postulación" not
"candidatura", "acostumbras" not "sueles", no vosotros, no
Spain-specific idioms.** The ask sounded like a translation cleanup;
the underlying need is systemic register enforcement: any new prompt
or string added tomorrow must inherit LatAm-ness without the
implementer remembering to specify it.

Related but distinct: Sonnet's own review pass used Spain-flavored
Spanish in its **suggestions** — meaning even our internal audit
tooling shares the default. LatAm has to be the anchored default,
not an opt-in.

## How we'll know it worked

Users stop reporting Spain-flavored strings in either UI text or
AI-generated output (cover letters, scoring reasoning, resume
summary). Second-order signal: any new prompt added to the codebase
automatically inherits the LatAm clause via
`core/settings.py:language_instruction`, without the implementer
having to know about it.

## Related

- Fix landed in `core/settings.py:language_instruction` (single
  point of enforcement; cascades to every prompt that calls it).
- Vision non-negotiable #4.
- Prompt-suite audit surfaced 4/8 prompts were missing the
  `language_instruction` call entirely — those were fixed in the
  same PR.
