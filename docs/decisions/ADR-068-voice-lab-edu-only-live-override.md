# ADR-068: Voice lab is -edu-only, file-logged, and tests Live through an override

Date: 2026-10-01
Status: Accepted
Relates to: REQ-046, REQ-044, ADR-063, ADR-052

## Context
We choose the coach's voice and delivery by guessing. Gemini has no pitch or rate knob. The real levers are the voice, a delivery instruction, and the Live-only toggles (affective dialog, proactive audio, VAD).

## Decision
- `/lab/voice` and its routes 404 unless `JOBOT_VOICE_LAB=1`, which is set only on -edu.
- **Takes come from the real Live model** (revised 2026-10-01). The first version used TTS, but TTS is a different model, so its delivery doesn't transfer to the coach. Each take is now one short Live session with the coach's own model, voice and config, in one of two modes. **Script** mode has Live read your line verbatim; its transcription is checked against the line. **Opening** mode runs the real P7 prompt and context. Every take keeps the **raw** audio plus the **Jobot pause-stretched** audio, using a Python port of the page's detect-and-stretch. Stretch knobs (min pause, target) are part of the config and the live override, so the page uses them in real sessions.
- **Measured on Live:** the same line was 9.0 s calm-slow vs 8.1 s upbeat-fast (TTS gave 11.5 s vs 7.6 s). Live mostly ignores pace instructions (as in ADR-054). The real levers are the voice and our stretch.
- **Takes, not A/B** (revised 2026-10-01, Eduardo): one settings panel. Every Play is recorded as a take in a side list, where each take can be replayed (session-stretched or raw), rated 1–5, liked, loaded back or deleted. Every Play makes a new take, because Live varies between calls. Stored in `voice_lab/takes.json` on the volume; there's no DB table.
- **Live test:** a saved override is applied inside `live._config` to real practice sessions, but only while the flag is on. The live page shows a "Lab" chip.
- Winners reach users only through a code change plus an ADR.

## Alternatives considered
- A separate lab live client: it would duplicate the 700-line runner.
- A DB table: it would add a schema change to every user's app for an internal tool.

## Consequences
While the override is on, every -edu practice session uses it. That's intended, and visible through the chip.
