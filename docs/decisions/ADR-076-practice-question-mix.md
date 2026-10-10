# ADR-076: Session mix = opener + role + character, rotated by code

Date: 2026-10-10
Status: Accepted
Relates to: REQ-049, ADR-056

## Decision
Plain sessions: one opener, role questions (the toolkit's), and 1 (quick,
standard) or 2 (full) **character** questions from a fixed, reviewed en/es
bank (`core/prep/character_bank.py`): wrong call, pushback, hard feedback,
competing priorities, getting a message across, growth area, a mistake under
a deadline, a moment outside your comfort zone, a plan restarting. Code picks the slots and
rotates: questions asked least recently (last 6 sessions) go first. Focus
drills and "missed cards" sessions stay pure.

## Why
A bank (not the LLM) keeps the copy ours and costs no regeneration; code-owned
slots make the mix the same every time. Character answers have no competency,
so they aren't in the by-competency score yet (like openers) — a "learned or
changed" check is the follow-up (REQ-042).
