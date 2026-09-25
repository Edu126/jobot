# ADR-049: Practice is a live-voice mock via Gemini Live

Date: 2026-09-21
Status: Accepted (deferred — later phase of REQ-041)
Relates to: REQ-041, ADR-047, ADR-048, D6/D10 (product decisions), GOV (consent — to write)

## Context
Practice is the centrepiece of the pack: an AI interviewer that "feels present
and human", one question at a time, at most one follow-up, with an animated orb
that shows idle/speaking/listening/thinking/follow-up states. The realism that
makes a mock not-homework is real-time voice, both directions. The alternatives
are turn-based text or a mic-in / text-out middle ground.

## Decision
Practice v1 targets **bidirectional live voice via Gemini Live** (streaming
audio in and out, the orb reacting to session state). The per-turn interviewer
behaviour is P7 (a system prompt, not JSON); answer evaluation (P8) and the
debrief (P9) run after the turn / session in code + JSON calls. Audio is **not
stored** by default (D10) — only transcript and feedback — and a consent screen
precedes the first session. This is deferred: we build the P1–P4 pipeline and
the Brief/Toolkit screens first; Practice lands once that foundation is real.

## Alternatives considered
- **Turn-based text first** — rejected as the v1 target: loses the delivery
  signal (pace, fillers) and the "feels real" bar the pack sets.
- **Mic-in / browser-TTS-out** — rejected: cheaper but the coach sounds robotic
  and half-duplex kills the follow-up-interruption realism.

## Consequences
The hardest, riskiest piece: websockets/streaming, audio capture + playback,
latency, and cost per session all become real concerns — hence deferred behind
the pipeline. A consent + audio-retention governance note (GOV) is owed before
the first byte of mic audio is captured. Reduced-motion and captions are
mandatory, not optional, for the orb.
