# ADR-068: Voice lab is -edu-only, file-logged, and tests Live through an override

Date: 2026-10-01
Status: Accepted
Relates to: REQ-046, REQ-044, ADR-063, ADR-052

## Context
We choose the coach's voice and delivery by guessing. Gemini has no pitch or rate knob. The real levers are the voice, a delivery instruction, and the Live-only toggles (affective dialog, proactive audio, VAD).

## Decision
- `/lab/voice` and its routes 404 unless `JOBOT_VOICE_LAB=1`, which is set only on -edu.
- **Line test:** TTS with the voice plus a delivery line, cached by config.
- **Blind A/B:** results are appended to `voice_lab/trials.jsonl` on the volume. There's no DB table.
- **Live test:** a saved override is applied inside `live._config` to real practice sessions, but only while the flag is on. The live page shows a "Lab" chip.
- Winners reach users only through a code change plus an ADR.

## Alternatives considered
- A separate lab live client: it would duplicate the 700-line runner.
- A DB table: it would add a schema change to every user's app for an internal tool.

## Consequences
While the override is on, every -edu practice session uses it. That's intended, and visible through the chip.
