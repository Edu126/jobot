# ADR-050: The interviewer is drawn client-side from played audio; we never send video to Gemini, and ES stays dark until `es-419` is confirmed

Date: 2026-09-16
Status: Accepted (design) — the 15-min / 2-min session caps this ADR rests on
are ⚠ snippet-sourced; **gate G4** confirms them before this leaves "design".
Relates to: REQ-041, ADR-047 (transport), ADR-003 (no build step), ADR-046
(typography), architecture vision non-negotiable #4 (LatAm-first Spanish),
research memo Pillar 3

## Context

Eduardo asked for a Zoom-like feel: *"una animación que se va a render desde el
lado del usuario, donde él con los waves que vamos recibiendo de Google va
moviendo la boca"*, explicitly *"para no estar haciendo mucho post-processing"*,
and possibly three interviewer avatars picked at random.

Research (Pillar 3) turned that preference into a hard constraint:

- **Session cap is 15 minutes audio-only, but 2 minutes with video.** A
  5-minute call is only possible in the audio-only lane.
- A mouth can be driven with **zero dependencies**: Web Audio `AnalyserNode` on
  the node that is already playing, RMS envelope per animation frame → mouth
  scale. Viseme-level options exist and are browser-native (wawa-lipsync, MIT;
  TalkingHead.js). **Rhubarb is an offline desktop tool over finished files and
  is unusable here.**
- **30 HD voices, 24 languages**, settable per session. **But `es-419` could not
  be confirmed** in Google's own supported-language table — only general Spanish
  / `es-ES`.

## Decision

1. **The session modality is audio-only. We never send video to Gemini, and we
   never ask Gemini for video.** The avatar is a *local rendering of audio we are
   already playing* — not a media stream. This is what keeps us inside the
   15-minute cap.
2. **Lip-sync v1 is the amplitude envelope**, not visemes: `AnalyserNode` →
   RMS → mouth scale, ~60 fps, no library, no build step (ADR-003 holds). A
   viseme library is a later upgrade, not a v1 dependency.
3. **The avatar is deliberately stylized, not photoreal.** An abstract or
   illustrated interviewer — the uncanny valley is a real risk at this emotional
   stakes level, and a stylized figure that moves well beats a realistic one that
   moves wrong. It also sidesteps every likeness question of a synthetic "person".
4. **One interviewer in v1**, one voice, warm and neutral. Three personas is a
   `voice_name` string away — technically free — but the cost is copy, testing,
   and three ways to feel wrong before we know anyone finishes a call.
5. **Spanish stays dark until `es-419` is verified.** If Google exposes only
   `es-ES`, an ES call ships **Spain register**, which is a regression against
   non-negotiable #4 — the one thing this codebase has systematically refused
   since `language_instruction()` existed. Until verified in AI Studio, the call
   is EN-only and the ES entry point says so honestly rather than shipping wrong
   Spanish. (Gate G2 in the research memo.)

## Alternatives considered

- **Send video / use Gemini's video modality.** Rejected: drops the session cap
  to 2 minutes and breaks the feature, for an avatar we can draw locally anyway.
- **Server-side audio analysis to drive the mouth.** Rejected — exactly the
  "mucho post-processing" Eduardo ruled out, and it would require the audio to
  pass through our box, which ADR-047 just removed.
- **Viseme-accurate lip-sync in v1** (wawa-lipsync). Deferred: a dependency and
  a tuning surface for a fidelity nobody asked for; amplitude reads as "talking"
  at conversational distance.
- **Photoreal avatar / video generation.** Rejected: cost, uncanny valley, and a
  synthetic-person likeness problem jobot has no reason to take on.
- **Ship ES with `es-ES`.** Rejected — see #5. Shipping wrong Spanish is worse
  than shipping no Spanish.

## Consequences

- **The avatar may not ship in the first slice at all.** REQ-041's thin slice
  replaces it with a listening/speaking state indicator, because it is the
  largest block of net-new client code and it sits downstream of the question
  that actually decides the feature (will anyone press Start). This ADR stays
  the design for *when* it ships; a face may also be the wrong thing to show a
  user on their very first call (REQ-041, Activation).
- The avatar costs **zero tokens and zero server CPU**. It is pure client
  rendering of bytes already in the browser's audio graph.
- We inherit a mobile constraint: audio autoplay and mic permission require a
  user gesture, and iOS Safari suspends the AudioContext on backgrounding. The
  call must start behind an explicit "Start" tap and handle suspension.
- **A bilingual product shipping an EN-only live call is a visible asymmetry**
  and must be stated plainly in the UI, not hidden. It is a temporary state
  gated on G2, and it is the honest one.
- Personas, realism dials and viseme fidelity are all additive later — none of
  them change the transport, the schema, or the modality.
