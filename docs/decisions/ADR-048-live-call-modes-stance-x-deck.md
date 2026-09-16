# ADR-048: The call framework is stance × deck, and the kit is its agenda — not a new content engine

Date: 2026-09-16
Status: Accepted (design)
Relates to: REQ-041, ADR-028 (prep_kits — the agenda), ADR-026 (prep_sessions),
ADR-021/REQ-018 (defense hooks), GOV-005 (practice ≠ cheat), ADR-005
(grounded-or-none), research memo Pillars 1–2

## Context

Eduardo asked for "un estilo de framework": feedback inmediato · conversación
completa con feedback al final · estilo life coach — plus the user choosing
**what** to review ("no de complejidad, pero sí qué cosas revisar").

Two research findings constrain the shape:

1. **Feedback timing has no clean winner** (Pillar 1). Immediate feedback wins
   same-session polish; **delayed feedback won 7 of 8 studies measuring
   retention ~1 week out** (Kulik & Kulik 1988). The real interview is the
   delayed test.
2. **Voice sessions need a built-in finish line** (Pillar 2) or they ramble and
   turn awkward — the pattern behind Speak's and Duolingo's bounded roleplays.

And one architectural fact: `prep_kits.star_qa` **already** carries
`why_you | behavioral | situational | culture_fit | defensive_gap`, grounded on
the real JD + résumé + known gaps, already gated grounded-or-none.

## Decision

**Two orthogonal axes. No difficulty slider.**

**Axis 1 — STANCE** (who is on the other side):
- **Simulation** — no interruptions, realistic interviewer, ~5 min, debrief
  afterwards (ADR-049). **This is the DEFAULT**, because the literature favors
  delayed feedback for transfer to an interview days away.
- **Drill** — interrupts with a short correction after each answer. Formative,
  for the nervous or first-time user. The ramp, not the hero.
- **Mentor** — exploratory, no evaluation ("cuéntame tu historia").
  **Deferred past v1** (see Consequences).

**Axis 2 — DECK** (what gets asked) = the kit's existing `kind` values, shown
as toggles: *presentación* (`why_you`) · *behavioral* · *situational* ·
*culture fit* · **defensa de gaps** (`defensive_gap`).

**The kit is the agenda.** The selected deck's questions are placed in the
session's system instruction as **the list to ask**, alongside the company
outlook, the JD and the résumé. The live model does not invent the interview;
it *conducts* one we already generated and already validated.

Consequences of that framing, all deliberate:
- **Grounding is inherited, not re-litigated.** The questions passed to the live
  session already passed ADR-028's grounded-or-none gate.
- **The call has a finish line**: N questions, then it ends. That *is* the
  "no más de cinco minutos" contract, enforced by content rather than a timer
  cutting someone off mid-sentence.
- **The model speaks first and the user answers before seeing any model
  answer** — retrieval practice, not recognition (Roediger & Karpicke 2006).
  The kit's own STAR text stays hidden during the call.
- If a session has **no kit** (generation failed, or an honestly-empty kit), the
  call **does not offer itself**. No ungrounded improvised interview.

## Alternatives considered

- **A difficulty slider (easy/medium/hard).** Rejected — it is what the whole
  category does, and Eduardo explicitly rejected it. Realism lives in the
  *interviewer's* behavior, not in question hardness. (The Pillar-2 lateral
  provocation — an interviewer who is distracted or unprepared, like real ones —
  is parked as a future realism dial, not a v1 feature.)
- **Generating fresh questions live, inside the session.** Rejected: a second
  content engine, ungrounded by construction, un-inspectable server-side
  (ADR-047), and it would put GOV-005 compliance inside an unobservable stream.
- **Ship all three stances at once.** Rejected — three surfaces, no data on
  which one people finish.
- **Let the model free-form the whole conversation from the JD.** Rejected for
  the same reason ADR-028 caches a kit: reproducibility and grounding.

## Consequences

- **Mentor mode is deferred**, despite being strategically the most valuable —
  it is the candidate-model acquisition mode wearing a practice costume (product
  vision: the "narrated career self"). It is also the one with the weakest felt
  value and no artifact to land in. It gets its own REQ when the debrief
  artifact exists to receive it.
- Adding a stance later is a prompt + a UI toggle, not a schema change.
- The deck toggles give us a free BI signal: **what people choose to rehearse**
  is a read on what they fear, per vacancy.
- If the kit is thin (thin résumé → few grounded STARs), the call is short or
  unavailable. Honest, and consistent with ADR-028's "better empty than
  fabricated".
