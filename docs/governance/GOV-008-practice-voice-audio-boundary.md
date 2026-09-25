# GOV-008: Practice voice — audio data boundary

Date: 2026-09-21
Relates to: REQ-041, ADR-049, ADR-051, D10 (product decisions)

## What data, where it goes
As of **ADR-052**, Practice-by-voice streams the candidate's **microphone audio
directly from the browser to Google Gemini Live** (the browser connects with the
`@google/genai` SDK using a server-minted ephemeral token). **The audio no longer
transits our server** — only the derived **text transcript** is POSTed back to us
at the end for the debrief. (Previously, ADR-051, audio was relayed through our
WebSocket.) No résumé, no PII beyond what the candidate chooses to say leaves the
browser as audio.

## Retention (D10 — the non-negotiable)
- **Audio is NOT stored.** The **live** conversation audio streams browser↔Google
  directly and never reaches us (ADR-052). For the **debrief**, the client uploads
  the candidate's recorded answers once (a WAV) to our `/audio` endpoint; the
  server forwards it to the Gemini File API for scoring and **deletes it right
  after** (ADR-053) — it is never written to our DB or kept on disk beyond that
  transient request. `practice_sessions.transcript_json` stores the **text**
  transcript and `debrief_json` the derived debrief/delivery numbers. That is all
  that persists.
- **New egress (ADR-053):** the candidate's answer audio now transits our server
  transiently for scoring (upload → Gemini File API → delete). Consent copy still
  holds ("audio isn't stored"); revisit if we ever want to retain audio.
- Google may process audio transiently to produce the response per their API
  terms; we send the minimum and keep nothing.

## Consent
The C1 consent screen (once, account-level `prep_practice_consent`) precedes the
first session and states plainly: the coach is an AI, audio isn't stored,
transcript + feedback are kept, and any session can be deleted. Mic capture
never starts before consent + an explicit browser permission grant.

## Controls
- The user can mute the mic mid-session and end the session at any time.
- Deleting a practice session (or its interview) removes its transcripts +
  feedback (CASCADE). There is no audio to delete — none was kept.
- Voice is **off unless `GEMINI_LIVE_MODEL` is configured**; absent it, Practice
  is text-only and no audio leaves the browser at all.

## Open risk
Live audio is a new egress path (previously only text hit Gemini, GOV-001).
Revisit if Gemini Live's terms change on transient audio handling.
