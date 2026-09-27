# ADR-054: Practice voice — manufacture breathing pauses client-side

Date: 2026-09-25
Status: Accepted, then partially reversed (see Update) — needs live QA on -edu
Relates to: REQ-041, ADR-052, ADR-053, ADR-055, GOV-008

## Update 2026-09-25 (A1 reversed)
Once ADR-055 let us SAVE + MEASURE the raw coach audio, the numbers showed Gemini's
native audio **already breathes** (~12% silence, a pause every few seconds, longest run
~2.8 s). The A1 client-side pause injection was therefore fighting the model and, because
transcript↔audio isn't time-aligned, dropped gaps mid-phrase ("AI [pause] coach" — Eduardo).
**A1 is removed; playback is now faithful (1.0 rate + jitter-buffer pre-roll).** The
turn-boundary beat (A2) and the `enable_affective_dialog` toggle (A3) stay. If we ever want
MORE pause, the right lever is "detect-and-stretch" the model's own gaps in the AUDIO (no
transcript alignment needed), not re-injecting from punctuation.

## Context
Eduardo's live QA of the voice coach: the reframed complaint isn't speed, it's that
the coach **doesn't breathe** — it reads sentences run together with no pauses. We
verified against google-genai 2.8.0 that **Gemini Live gives no server/prompt control
over pacing or pauses**: `SpeechConfig` (Live) exposes only voice/language/multi-speaker;
`speaking_rate`, `speech_metadata.style`, and the `<breath>`/`<short pause>` vocal tags
are **TTS-API-only** and not honored by native-audio Live; system-prompt pacing
directives are largely ignored (a widely reported Live limitation). Our Live model is
`gemini-3.8-live` (native audio).

## Decision
Pauses are **manufactured on the client** (`practice_live.html`), since the API can't:
- **Within-turn gaps (the core fix):** when the streamed `outputTranscription` hits a
  sentence end (`.!?` → ~350 ms) or clause end (`,;:—` → ~150 ms), drop that much
  silence into the playback timeline (`_playHead`) before the next audio chunk, so the
  coach pauses between its own sentences. Alignment is approximate (transcript vs audio
  lag) — the constants are tunable and start conservative.
- **Turn-boundary beat:** ~400 ms after `turnComplete` before the mic reopens.
- **Softened playback rate:** 0.92 → 0.97 (the earlier uniform slow-down was the wrong
  lever now that discrete gaps do the pacing).
- **`enable_affective_dialog` A/B:** env-gated (`GEMINI_AFFECTIVE_DIALOG`, default off)
  in `_config()` — the only server-side naturalness lever available on native audio.

## Alternatives considered
- **Prompt / vocal tags / speaking_rate** — rejected: not supported on Live (verified).
- **Re-architect to Gemini TTS / half-cascade** for true prosody control — deferred
  post-beta: it would lose Live's low-latency streaming, automatic VAD, and barge-in
  (breaks ADR-052) and require app-orchestrated turns.

## Consequences
Pause timing is best-effort, not exact — good enough to "breathe," tunable if gaps land
off. No new egress or data surface. If A1–A5 aren't enough after QA, the TTS
rearchitecture is the documented next step.
