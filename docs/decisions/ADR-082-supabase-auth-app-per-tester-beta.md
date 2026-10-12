# ADR-082: Supabase Auth now; one app per tester for the Reddit beta

Date: 2026-10-12
Status: Accepted
Relates to: REQ-054, ADR-001, ADR-083

## Context
We want 6 users plus about 20 Reddit testers signed in within 30 days.
Today there is no login, only private URLs. Eduardo picked Supabase,
Google sign-in with an email code as backup, manual approval, and a budget
of $25 a month or less.

## Decision
Use Supabase Auth only. Each app keeps its own SQLite file and allows a
single email (`OWNER_EMAIL`). Testers come in through the waitlist, a
manual approval, a script that creates their app, and a Supabase invite.
Emails go out through Resend over SMTP. Staging (-edu) and the admin
pages allow only Eduardo.

## Alternatives considered
- Cloudflare Access: needs no code, but it's a second identity system we'd drop later.
- Our own Google sign-in: thrown away later.
- Move the whole database to Supabase now: weeks of work before Reddit.

## Consequences
Free Supabase projects pause after a week with no activity, which locks
everyone out. We need a daily keep-alive, then Pro once testers arrive.
Every tester is one more app to deploy and, later, to migrate (ADR-083).
