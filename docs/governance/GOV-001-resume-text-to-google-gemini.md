# GOV-001: Resume text sent to Google Gemini

Date: 2026-08-21
Relates to: ADR-004 (Gemini as POC LLM), REQ-003 (grounded AI
summary — governs the same data flow)

## Data involved

The **full parsed resume text** (up to 12,000 chars per call for
scoring; up to 8,000 for AI summary + search suggestions; up to
12,000 for re-parse). Contents typically include:

- Full name, email, phone, LinkedIn URL, home city / country
- Complete work history: employer names, titles, dates, achievement
  bullets (often mentioning clients, project scope, sometimes
  financial figures)
- Education: institution, degree, dates
- Certifications, languages, references (if the user included them)
- Sometimes: personal statement, salary expectations, availability,
  work-authorization status

Sensitive by any definition — this is the user's professional
identity, in one string, sent verbatim to an external API on every
score/tailor/summary/regenerate call.

## Who can access it

- **Google** (the API operator). Free-tier terms as of 2026-08
  allow Google to use inputs for model improvement unless the paid
  tier is used. We are on the free tier (see ADR-004). See
  <https://ai.google.dev/gemini-api/terms>.
- **Fly.io** (network operator carrying the outbound HTTPS traffic).
  TLS-encrypted in flight, decrypted at Google's edge.
- **The operator** (currently: user + Claude via `fly ssh console`)
  — can read the resume from the SQLite volume at any time.
- **Anyone with `fly ssh` access to the app** — currently
  operator-only, mediated by `FLY_API_TOKEN` in GitHub Actions
  secrets and the operator's local `flyctl` auth.

## Where it lives and where it travels

- **At rest:** SQLite `resumes.parsed_json` blob on the Fly volume
  attached to each per-user app. Physical isolation between users
  (one file per user, ADR-002).
- **In flight:** every AI call (`core/matching/semantic_score.py`,
  `core/llm/`, `ui_web/routes/profile.py:_maybe_generate_ai_summary`,
  `core/resume/ai_regenerate.py`) sends the resume (or a substring
  of it) as part of the prompt payload over HTTPS to
  `generativelanguage.googleapis.com`.
- **Return path:** JSON response body includes model reasoning that
  may quote resume snippets back (esp. `first_impression_evidence`
  in the AI summary since REQ-003 landed). No new resume data
  created.

## Risk accepted

- **Google free-tier data retention.** Google may use resume text
  to improve models. Four real beta users; all know jobot uses AI
  and provided their own API key (implicit opt-in through the
  Profile setup flow). Acceptable during POC.
- **No user-facing disclosure at the moment we send the resume**
  (no "resume sent to Google" banner). Users are aware in aggregate
  but not per-call.
- **No selective redaction.** Contact info + salary references + all
  free-text is sent as-is. A future feature could strip PII before
  send (Phone, email, LinkedIn); we haven't built it.
- **No audit log of what was sent.** We know per-identity call
  counts + token totals (`core/llm/usage.py`), not payload
  contents.

## Revisit when

- We monetize / open to non-personal users (need explicit
  opt-in disclosure, likely a per-user consent flag, likely a shift
  to paid tier to eliminate the training-data question).
- We add a user in a jurisdiction where sending resume text to a US
  cloud + Google is problematic without consent (GDPR territory,
  which already includes Sara in Spain — currently accepted because
  she personally consented).
- Google changes free-tier data-retention terms (probable trigger
  for the multi-provider migration mentioned in ADR-004).
- We add a "delete my data from Google" affordance (not currently
  possible — Google's free tier gives us no user-scoped deletion
  API).
