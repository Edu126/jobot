# ADR-002: SQLite as the POC database

Date: ~2026-07 (documented retroactively 2026-08-21)
Status: Accepted (POC) — decision explicitly open for revisit,
particularly against Supabase which would bundle auth as a
side-effect.

## Context
Building fast during POC. Needed a persistence layer immediately.
Python has `sqlite3` in stdlib; a file-based DB fits the one-Fly-app-
per-user architecture (see ADR-001) cleanly — one volume, one file,
one user.

## Decision
Use SQLite via the stdlib `sqlite3` module, no ORM. One `data/jobot.db`
per Fly volume. Schema managed by idempotent DDL (`CREATE TABLE IF
NOT EXISTS ...`) with a monotonic `SCHEMA_VERSION` bump on structural
changes. Backup = file copy.

## Alternatives considered
Honestly, none were weighed at decision time. Post-hoc, the real
candidates are:
- **Postgres on Fly.** Better concurrency (SQLite is single-writer);
  richer JSON queries; adds a separate service to run, cost > $0 above
  the free instance.
- **Supabase.** Would bring **free magic-link + Google auth** as a
  side-effect — that's the most interesting angle given the planned
  multi-user migration. Also adds realtime + row-level security
  primitives we'd otherwise build ourselves.

## Consequences
- Zero database ops, zero cost.
- File-per-user is a **privacy feature** (physical isolation, not
  policy). Backing up one user = copying one file. Deleting one user
  = removing one volume.
- SQLite's single-writer model has been fine at 4 users; will not
  scale linearly to hundreds.
- If we migrate to Supabase for auth, we **lose the file-per-user
  isolation guarantee** — that's a real trade-off that isn't yet
  weighed. Per-user isolation would then be enforced by RLS policy,
  not physics. See vision.md non-negotiable #3 (the guarantee
  survives; the mechanism does not).
- Any migration off SQLite requires exporting data per-user (since
  each user has their own volume today) and rehydrating into the new
  store. That's per-user migration, not a single lift-and-shift.
