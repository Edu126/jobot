# ADR-052: Practice voice — browser connects directly to Gemini Live via an ephemeral token

Date: 2026-09-22
Status: Accepted (needs live QA on -edu)
Relates to: REQ-041, GOV-008, supersedes ADR-051 (relay transport + app-driven turns)

## Context
ADR-051 built voice as a **server WebSocket relay** with an **app-orchestrated,
per-question turn state machine** (`send_client_content("say this", turn_complete=
True)` per question; mic forwarded only during a "listening" phase; manual
"Finish" button). Live QA showed it was fundamentally broken: the docs state
`turn_complete=True` **unconditionally interrupts generation**, so injecting the
next question stalled the coach after the welcome; the phase-gated uplink meant
the candidate was often never heard and there was no mic-activity signal; the
hand-rolled `ScriptProcessor` capture + manual PCM playback (no `interrupted`
handling) buzzed; and it felt scripted, not conversational. Root cause: we
re-implemented transport + VAD + turn-taking + audio, fighting Gemini Live's own
automatic VAD.

## Decision
The **browser connects directly to Gemini Live** with the official `@google/genai`
SDK, using a single-use **ephemeral token** minted server-side
(`client.auth_tokens.create`) whose `live_connect_constraints` **pin** our model,
P7 system instruction (+ candidate/company context), voice, transcription, and
AUDIO output — the client cannot change them. The **model conducts the whole
interview** (welcome → questions in order → one follow-up → close) using
**automatic VAD**: mic streams continuously, turns are hands-free, barge-in works.
The browser shows a live two-sided transcript + a mic VU signal, and on end POSTs
the **text transcript** to us for a **holistic debrief** (`session_debrief_from_
transcript`). Delivery numbers are computed over the candidate's turns. The typed
runner keeps the structured per-answer P8 path. Env-gated by `GEMINI_LIVE_MODEL`;
any failure falls back to the text runner.

## Alternatives considered
- **Keep/fix our relay (model-driven)** — rejected: we'd still own the fragile
  browser audio + a WS proxy for no benefit over a direct connection.
- **Managed voice-agent framework (Pipecat/LiveKit)** — deferred: most robust but
  new infra + cost, overkill for one feature today.

## Consequences
Mic audio now egresses **browser → Google directly**, not through our server
(GOV-008 updated — still never stored). We lose per-answer P8 "stronger version"
for voice (holistic debrief instead) — accepted trade for a fluid conversation.
New client dependency (@google/genai via ESM CDN) + AudioWorklet in the browser.
The old WS route + `_Bridge` are deleted. `transcript_json` added to
`practice_sessions` (migrated).
