# ADR-073: The coach's visual is the voice-only "wave"

Date: 2026-10-07
Status: Accepted. Supersedes the floating-head look of ADR-067 (its streamed captions still stand).
Relates to: REQ-047, ADR-067, ADR-052

## Context
Eduardo didn't like the floating 3D head ("does not look nice to me"). He wanted something voice-only: Siri-like, ethereal, less AI. The avatar lab (REQ-047) showed four voice-only variants. He picked **Wave**.

## Decision
The live practice draws `VoiceVisuals.make('wave', canvas)` from `static/voice_visuals.js`. Everyone with voice practice gets it, with no setting. `voiceOrb()` keeps only the audio graph: playback, echo-cancel routing, analysers. It feeds the wave the state plus real energy: coach RMS while the coach speaks, mic RMS while the candidate speaks. The head drawing code is deleted.

## Alternatives considered
- A user setting to pick the visual: an extra toggle for no real need (simplicity over escape hatches).
- Keep the head as an option: Eduardo rejected the look.

## Consequences
The coach has no face, which is calmer and fits the HR-interviewer register. The other three variants stay in the lab for later.
