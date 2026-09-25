# ADR-050: The Story Bank is "account-level" = keyed on the candidate (resume_hash)

Date: 2026-09-21
Status: Accepted (REQ-041, Story Bank / D4)
Relates to: REQ-041, ADR-047, the v17 candidate-key convention

## Context
The pack (D4) says the Story Bank lives at the **account level** — stories are
reused across interviews, not scoped to one. But Jobot has no account
abstraction: deploys are single-tenant (one Fly app per user), "identity" is
just an IP/cookie for LLM rate-limiting, and every durable table (jobs,
prep_sessions, interviews) keys its owner as `resume_hash` — the v17 candidate
key (the text hash of the current résumé). There is no user_id to hang stories
off.

## Decision
Key `stories` on **resume_hash**, exactly like interviews. Within this
architecture that IS the account: a single deploy's candidate. P3 story-mapping
lists the bank by the interview's resume_hash, so stories flow across every
interview built against the same résumé.

## Alternatives considered
- **Deploy-global stories (no owner column)** — rejected: breaks the
  resume_hash pattern every sibling table follows, and pre-commits us against a
  future multi-résumé/account world.
- **Invent a real accounts table now** — rejected: no auth exists; premature,
  and nothing else would use it.

## Consequences
Uploading a *new* résumé (new text_hash) starts a fresh, empty bank — worse here
than for interviews, because stories are hand-crafted/voice-recorded assets with
real user investment. Accepted for v1 (a single user's résumé text is stable);
if résumé-swap-loses-stories bites, migrate to a stable account key (a one-time
backfill, not a schema redesign — the column just stops being resume_hash).
