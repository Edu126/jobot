# ADR-001: One Fly.io app per user for the POC phase

Date: ~2026-07 (documented retroactively 2026-08-21)
Status: Accepted (POC) — planned to be superseded by a multi-user
architecture with row-level security once beta feedback is collected.

## Context
We had 4 real people (Melissa, boyfriend, Sara, +1) willing to beta
test jobot. The alternative to giving each their own deployment was
building multi-user auth (login, sessions, RLS, user table) up front.
That would have delayed getting the app in front of real users. The
POC constraint was time-to-first-real-feedback, not long-term
scalability.

## Decision
Deploy one Fly.io app per user, each with its own SQLite volume, no
shared infrastructure, no auth. The whole-app-is-per-user architecture
substitutes for auth during the POC.

## Alternatives considered
- **Multi-tenant with row-level security up front.** Rejected: too
  much scaffolding (auth, sessions, per-user row-level policies) for a
  POC still validating the core value prop.
- **Users self-host locally.** Rejected: friction for non-developers;
  no way to observe real usage centrally.

## Consequences
- 3× (now, potentially more) infrastructure to manage. Fly's hobby
  plan makes cost near-zero, but deploys, secrets, and volume
  operations happen per-app. GH Actions matrix handles this cleanly
  today; it will not scale past ~10 users.
- Per-user data isolation is free — physically, not by policy.
- We are accepting **migration debt**: the planned move to multi-user
  with RLS (~2 weeks after POC feedback) will require a data
  migration for each existing user's SQLite → shared DB, plus retiring
  the per-app Fly deployments. That's real work we've deferred.
- Zero cross-tenant risk during POC — there is no other tenant.
- The historical Fly app names became a UX confusion (`jobbotv2-melissa`
  is actually Sara's app, etc). Kept as-is because renaming Fly apps
  is destructive; documented in `project_sprint_state.md` memory.
