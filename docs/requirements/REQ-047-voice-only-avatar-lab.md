# REQ-047: A lab to design the coach's avatar (voice-only looks)

Date: 2026-10-07
Source: Eduardo
Status: Decided 2026-10-07. Eduardo picked **Wave** and it now drives the live practice for everyone ([ADR-073](../decisions/ADR-073-coach-visual-is-the-wave.md)). The lab stays at `/lab/avatar` (-edu only) for future tuning.

## What they asked for
> "Generate a tab where we can design the other avatars. I want to try something more voice-only, like a Siri wave style, or something more geometric 3D like the loading screen. Something more ethereal, or something less AI. The current 3D model we have does not look nice to me."

## What they actually need
The floating head (ADR-067) reads as a gimmick. The coach should feel calm and human, like a professional on a call, not a character. Eduardo needs to see several candidate looks react to the same conversation (idle, coach speaking, candidate speaking, thinking), with his own voice, before choosing, so the choice is by eye and ear rather than by description.

## What we built
Four variants behind one interface, `makeX(canvas) -> { frame(state, level, t), destroy() }`: Wave (Siri-style layered sines), Ethereal (blurred breathing gradients), Geometric (rotating wireframe icosahedron plus pulse rings echoing `.gen-orb`), Minimal (one breathing circle). A state picker, a synthetic speech-like level, and a mic mode. The current head is not embedded (it is tied to the live audio graph); compare in a real session.

## How we'll know it worked
Eduardo picks one look. Promoting it is a one-line swap in `practice_live.html` (replace voiceOrb's drawing with `VoiceVisuals.make(name, canvas)`) plus an ADR superseding ADR-067.

## Related
REQ-046, ADR-067, ADR-068, design.md §2A
