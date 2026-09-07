# REQ-022: Structured profile parse — typed Summary / Experience / Skills / Education

Date: 2026-09-03
Source: Eduardo (product architect)
Status: **Deferred / not scheduled.** Captured so the intent isn't lost. Behind
the Preparation-tab work in priority — do NOT start until the parse-quality
question below is answered.

> Carved out of REQ-021. Phase A shipped the Profile shell but deliberately kept
> **Tab 1's generic parsed-section readout** — the deterministic dump of whatever
> sections `core.resume.anomalies` detects. This REQ is the follow-up: replace
> that dump with **typed modules** (Executive Summary · Work Experience timeline ·
> Detected Skills · Education).

## What they asked for

Eduardo's original REQ-021 mockup: Tab 1 as four fixed, well-styled blocks —
*Executive Summary* (paragraph), *Work Experience* (dated timeline of role /
company / achievements), *Detected Skills* (classified pills), *Education &
Certifications* (list).

## What they actually need — and why it's blocked

Typed modules need a parse that reliably classifies résumé content into those
buckets. We don't have that. The current parser emits loosely-detected sections,
and the mockup itself exposed the failure: its *Detected Skills* leaked
`Solution` and `Huminity` — token-parse junk. Promoting the readout to fixed
titled modules makes that garbage **more** prominent, not less. So the real work
here is **parse quality**, not layout — the layout is the easy 20%.

## The open technical question (resolve before building)

How do we get clean typed fields?

1. **Heuristic mapping** on existing detected section titles → cheap, but brittle
   with unconventional headings; doesn't fix the junk tokens.
2. **LLM structured parse** — one typed extraction call returning
   `{summary, experience[], skills[], education[]}`. Faithful, but it's a NEW
   LLM call site (ADR-008: JSON contract, language_instruction, llm-surface
   entry, cost) and needs a Pydantic contract + grounding guard so it can't
   hallucinate experience.
3. **Adopt a résumé schema** — e.g. **JSON Resume** (`jsonresume.org`) as the
   canonical typed shape the parser targets and the UI renders. Gives us a
   stable, well-specified contract (basics / work / education / skills) instead
   of an ad-hoc dict, and could later power export/import. Worth evaluating as
   the target schema for option 2's output.

Recommendation to revisit at scheduling time: **option 2 emitting an option-3
(JSON Resume) shape**, gated behind a grounding check like `ai_summary`'s.

## Scope guardrails

- **In (when scheduled):** typed extraction into Summary/Experience/Skills/
  Education with a grounding guard; the Tab 1 module layout from the mockup;
  graceful fallback to today's generic readout when extraction is low-confidence.
- **Out:** anything on Tab 2 (gap map); Add Languages (dropped in REQ-021); the
  header (done); export/import of JSON Resume (a possible later payoff, not this).

## How we'll know it worked

A user opens *My Profile & Skills* and sees their résumé as clean, correctly-
bucketed sections — no junk tokens in Skills, experience on a real timeline —
and trusts it as "yes, this is how Jobot read me."

## Related

REQ-021 (the shell this completes; kept the generic readout on purpose), ADR-008
(no free LLM call sites — option 2/3 must register on llm-surface), REQ-003 /
ADR-013 (`ai_summary` grounding guard — the pattern to copy), product vision
(Profile as the persistent career-persona surface). Priority note: the
**Preparation tab** (interview/application support) is the real next priority;
this parse work waits behind it.
