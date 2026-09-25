# ADR-051: Practice voice — WebSocket relay to Gemini Live, env-gated with a text fallback

Date: 2026-09-21
Status: Superseded by ADR-052 (the relay + app-driven turns proved unfit in live QA)
Relates to: REQ-041, ADR-049, GOV-008, the turn-based Practice machine

## Context
ADR-049 set live voice as Practice's v1 target. The turn-based machine
(session → per-answer P8 → P9 debrief → Feedback) is built and verified in text.
Now the voice layer sits on top. Two hard realities shaped this: (1) audio can't
be verified in code — it needs a real browser + mic on -edu; (2) the exact
Gemini Live model id for this key is unknown (the repo's model names run ahead),
and Live carries session/audio cost the JSON calls don't.

## Decision
Voice is a **WebSocket relay**: browser mic (PCM16 16 kHz via AudioWorklet) →
FastAPI WS → `client.aio.live` session (system_instruction = P7, response
modality AUDIO, input+output transcription on) → coach audio (PCM 24 kHz) +
transcripts streamed back → browser plays audio + drives the orb + captions.
Turns are **app-orchestrated per question** (not free-form): the coach voices
each session question, listens, and the captured input-transcription becomes that
answer — so the existing per-answer P8 + P9 machine is reused unchanged.

It is **env-gated by `GEMINI_LIVE_MODEL`**: unset → voice is hidden and Practice
stays text-only (the verified path). Any WS/model failure **falls back to the
text runner** — voice never breaks Practice. Audio is never stored (GOV-008).

## Alternatives considered
- **Browser Web Speech (SpeechSynthesis + SpeechRecognition)** — lower risk, no
  cost, works today, but lower fidelity and not the "feels present" bar; rejected
  as the target (kept in mind as a future fallback tier).
- **Model-driven free-form conversation** (P7 sequences everything) — rejected
  for v1: hard to segment into per-answer transcripts for P8, and non-deterministic.
- **Hardcode a Live model id** — rejected: unknown/volatile; a wrong id would
  break silently. Env var lets it be set without a deploy.

## Consequences
A new audio egress path (GOV-008) and a new real-time surface (WS, AudioWorklet,
sample-rate handling) that will need live debugging with the user — accepted, and
contained by the text fallback. Follow-ups (P7's one-follow-up) and the full
free-form conversational mode are deferred refinements on this transport.
