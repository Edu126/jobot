# ADR-033: Web-first is the primary posture; mobile is the exception

Date: 2026-09-07
Status: Accepted
Relates to: REQ-027 (presentation/onboarding page), ADR-003 (HTMX/Alpine stack)

## Context
Design discussion drifted toward "mobile-first" by default habit. Reality of the
job-hunt job-to-be-done contradicts it: people search and apply at a **desktop**,
where they have Word, many browser tabs, copy-paste into ATS forms, and room to
manage a pipeline of applications. The demoralizing, high-load work happens on a
computer, not a phone.

## Decision
**Web/desktop is the primary posture.** Design core surfaces (results, JD ↔
artifact side-by-side, gap map, the landing/onboarding page, the manual) for a
wide workspace and denser desktop reading. Mobile is a **supported exception**,
not the default — the genuinely mobile slice is interview **prep** (STAR review,
reverse questions on the go).

## Alternatives considered
- Mobile-first: contradicts where the actual work happens; cramps the workspace.
- Fully responsive parity: real cost for surfaces users won't touch on a phone.

## Consequences
Layouts optimize for width first; mobile gets graceful degradation, not equal
investment. Prep surfaces stay phone-friendly. Revisit if usage data shows
meaningful mobile application behavior. Does not change the ADR-003 stack.
