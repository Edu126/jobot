# GOV-002: `/admin/pulse` has no authentication

Date: 2026-08-21
Relates to: ADR-001 (single-tenant architecture — the whole-app-is-
per-user substitution for auth is the reason this exists at all)

## Data involved

The weekly BI pulse report contains:

- Aggregated engagement stats (event counts by type + day)
- Funnel numbers (surfaced → viewed → saved → applied → dismissed)
- Match-quality distribution + specific high-score dismissed job
  titles + companies
- **Verbatim feedback quotes**, truncated to 300 chars, with
  **identity attribution** (`sid:xxxx` cookie hash or `ip:x.x.x.x`)
- Stuck-state details: application titles, resume filenames,
  running search task IDs
- Gemini usage totals per model per day

The feedback quotes are the sensitive piece — user-written text
sometimes contains complaints about specific pages, occasional
personal context ("no puedo aplicar en Bogotá"), and the identity
tag lets a reader correlate quotes to sessions.

## Who can access it

- **Anyone who knows the URL** — `https://<app>.fly.dev/admin/pulse`.
  No login. No API key. Rate-limited (30/hour per identity) but not
  auth-gated.
- **URL-scanning bots** if they enumerate `/admin/*` — no
  robots.txt exclusion, no security-by-obscurity claim.
- **The operator** (obvious, intended reader).
- **The user themselves** — could stumble on it (nothing prevents
  them from typing `/admin/pulse` in their own app URL bar).

## Where it lives and where it travels

- **At rest:** `admin_reports` table in the per-user SQLite volume.
  Each user's pulse only contains their own data (ADR-001), so a
  URL leak on one app exposes only that user's pulse, not others'.
- **In flight:** rendered from the `markdown_it` HTML pipeline on
  request; HTTPS to the visitor. Nothing else outbound.
- **Third-party visibility:** the `markdown-it-py` renderer runs
  server-side; no CDN calls from the pulse page itself beyond the
  shared base template CDN loads (see the deferred GOV note on
  CDN-third-party — not written yet).

## Risk accepted

- **URL is guessable.** `/admin/pulse` is not a secret path. A
  motivated attacker or a curious user who saw the URL in a
  Sonnet/Opus review screenshot could reach it. This risk is
  accepted during POC because:
  1. Each app is single-user; the only feedback in a pulse is the
     user's own words (they wrote it, they can see it).
  2. Identity attribution (`sid:xxxx`) is a session-cookie hash,
     not a resolvable identifier.
  3. Rate limit (30/hour) prevents enumeration-scale scraping.
- **No CSRF / no anti-scanning.** The route is a GET with no state
  change. Read-only exposure only.

## Revisit when

- **We ship multi-user** (the biggest trigger, planned per ADR-001
  supersede). At that point one user's pulse could contain another
  user's feedback quotes — auth becomes mandatory. This is a hard
  gate: no multi-user launch until `/admin/pulse` is auth-gated.
- **We add real auth** (magic-link + Google, per Vision "Post-POC
  direction"). The admin route should be gated behind an `is_admin`
  role from that same auth system, not a separate mechanism.
- **A user shares the URL publicly** — unlikely (no reason to), but
  would justify accelerated auth work.
- **We add sensitive content to the pulse** beyond what's in the
  report today — e.g. raw resume text, scoring justifications,
  contact info. Today's content is intentionally limited to
  aggregates + already-user-written quotes.
