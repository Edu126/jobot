# ADR-053: Practice — score the debrief from raw audio; interviewer personas; split prompt

Date: 2026-09-22
Status: Accepted (needs live QA on -edu)
Relates to: REQ-041, ADR-052, GOV-008; informed by the Alvalens "Interview Live" write-up

## Context
Live QA + the Alvalens article surfaced three things. (1) The Live **streaming
transcript is unreliable** (wrong language / truncated), so a debrief built from
it is weak. (2) Users want to pick the **interviewer** (personality + voice), not
just a voice. (3) Undocumented Live behaviours bit us: system instructions over
**~4000 chars silently hang** the session (our P7 + context + questions exceeded
it), and the coach's audio **echo-loops** into the mic on speaker.

## Decision
- **Score from raw audio.** The browser records the candidate's answers and
  uploads a WAV at session end; `core/prep/audio_score.py::score_from_audio`
  sends it to an audio-capable model (`AUDIO_SCORE_MODEL`, default
  `gemini-2.5-flash`) → the P9-shaped debrief **plus delivery read from the audio**
  (wpm, filler count, pace, confidence) + an accurate transcript. Audio is
  uploaded to the Gemini File API transiently and **deleted after** (GOV-008
  updated). Falls back to the transcript-based debrief on failure.
- **Interviewer personas.** Three personas (Maya/friendly HR, David/direct hiring
  manager, Sam/supportive mentor) shown as a dropdown in setup; each bundles a
  voice + a style folded into the P7 core prompt; the choice is pinned in the
  ephemeral token. Persisted as `practice_sessions.persona`.
- **Split prompt** (fixes the silent hang): the pinned system instruction is the
  SHORT persona core only; the candidate/company context + questions ride in a
  separate `interviewer_context_turn`, injected by the client via
  `sendClientContent` after connect.
- **Echo defence + session resumption:** client-side mic gating (no mic while the
  coach speaks; resume 300 ms after `turnComplete`) + a grace period (mic off
  until the first coach audio); VAD LOW/700 ms; `session_resumption` + a
  reconnection guard for the ~10-min GoAway.

## Alternatives considered
- **Keep transcript-only feedback** — rejected: the transcript is too unreliable
  for trustworthy delivery/content scoring.
- **Relay the live audio through our server** (to score server-side, like the
  article) — rejected: gives up ADR-052's simplicity; instead the client uploads
  only the answer WAV at the end.

## Consequences
A new audio egress path (GOV-008): the answer audio transits our server + Gemini
File API transiently, never stored. Half-duplex during the coach's turn (no
barge-in) — accepted to kill the echo loop. A second model in the surface
(`gemini-2.5-flash` for scoring, alongside `gemini-3.8-live`). Video/non-verbal
scoring remains out of scope.
