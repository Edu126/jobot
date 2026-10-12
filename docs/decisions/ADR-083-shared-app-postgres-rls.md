# ADR-083: The shared app runs on Supabase Postgres with row-level security, built during the beta

Date: 2026-10-12
Status: Accepted (design during the beta; build follows)
Relates to: ADR-001, ADR-002, ADR-082, vision.md #3

## Context
One app per user stops scaling at about 30 users. The schema has 33 tables
and about 221 SQL statements across 11 files. In a shared app, one query
that forgets to filter by user would show one person's résumé to another.
That is the failure that would break the privacy promise.

## Decision
- Build one shared app on Supabase Postgres while testers use the beta.
- Every user-owned table gets `user_id`, with RLS policies scoped to `auth.uid()`.
- The app connects as the user, never with the service-role key, on request paths.
- An isolation test suite (user A can never read user B) gates the merge.
- New testers start there. The 6 existing users migrate last, with their IDs remapped.

## Alternatives considered
- Shared SQLite with `user_id` in code: no database-level guarantee.
- Postgres on Fly: we'd run auth and RLS ourselves.

## Consequences
Two topologies run side by side for a few weeks. Job-search results become
shareable across users (public postings), so the cache gets faster.
