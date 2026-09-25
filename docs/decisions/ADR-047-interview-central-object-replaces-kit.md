# ADR-047: The Interview is the central prep object — replaces the per-vacancy kit

Date: 2026-09-21
Status: Accepted (phased build; REQ-041)
Relates to: REQ-041, supersedes ADR-026 / ADR-027 / ADR-028 at parity

## Context
Prep today is a per-VACANCY session (ADR-026): a bound job, a lazy company
outlook (ADR-027), and a read-only STAR/reverse kit (ADR-028). The pack asks
for a richer object that also holds a round type, date, interviewer title,
recruiter notes, derived competencies, practice sessions, debriefs, and a
readiness band — and that survives across the four steps Brief → Get Ready →
Practice → Feedback. Bolting these onto `prep_sessions` would overload a table
whose semantics ("a vacancy I got a callback for") no longer fit.

## Decision
Model an **Interview** as the central object (one role + one company + one
round) in a new `interviews` table, with generated artifacts (brief, questions,
mapping, flashcards, debriefs) cached in a generic `prep_artifacts` store keyed
(interview_id, kind, lang, prompt_version). The new module is the canonical
Prep. The old kit stays live until the new screens reach parity, then its
routes/tables are retired — no big-bang deletion.

## Alternatives considered
- **Extend `prep_sessions` in place** — rejected: overloads vacancy semantics,
  and the four-step lifecycle wants its own status machine.
- **Keep both tabs permanently** — rejected: two Preps confuse the user and
  double the maintenance; the pack says one central object.

## Consequences
A migration window where both systems coexist (accepted, time-boxed). Company
research now caches per-company, not per-interview, so 3 rounds at one company
share one Tavily call — a change from the per-session outlook cache. Retiring
ADR-026/027/028 code is deferred work we must not forget.
