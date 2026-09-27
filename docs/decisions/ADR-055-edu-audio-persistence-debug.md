# ADR-055: Persist practice audio on -edu (debug, opt-in) — scoped GOV-008 exception

Date: 2026-09-25
Status: Accepted
Relates to: GOV-008, ADR-052, ADR-053, ADR-054

## Context
Eduardo reports the live coach "still sounds very AI," and notes the SAME model sounds
fine in Google's AI Studio playground — pointing at OUR audio send/playback, not the
model. To turn that from opinion into an A/B, we need the **raw coach audio our client
receives from Gemini** (before any playback processing) as a file, plus a way to measure
its pacing objectively. GOV-008 says practice audio is **never stored**, which blocks this.

## Decision
Add an **-edu-only, opt-in, deletable** debug persistence path — a **scoped exception**
to GOV-008, never active in production:
- Gated by env `JOBOT_SAVE_AUDIO=1`, set only on the -edu staging app (`prep_live.save_audio_enabled()`).
- The client uploads the RAW coach PCM (24 kHz) captured in `enqueue()` alongside the
  existing candidate WAV; `_persist_practice_audio` writes both to the Fly volume at
  `data/practice_audio/` (`prep_live.saved_audio_dir()`). Best-effort, never fatal.
- Listed/downloaded via `GET /interviews/practice/audio[/{file}]` (name-sanitized,
  flag-gated → 404 when off).
- `core/prep/audio_metrics.py` measures pacing (pauses, ratio, WPM) from a WAV — my
  objective read (I can't hear timbre; Eduardo judges that by ear).

Prod is unaffected: the flag is off, so the code path that writes audio never runs and the
GOV-008 "never stored" guarantee holds for real users.

## Alternatives considered
- **Keep audio fully ephemeral** — rejected: without the raw file we can't A/B against the
  playground or measure pacing; the "sounds AI" bug stays subjective.
- **Store for all users** — rejected: violates GOV-008 for real users with no benefit.

## Consequences
On -edu only, Eduardo's practice audio (his voice + the coach) is written to the volume
until deleted. Acceptable: -edu is his own box with his own data (verify-on-edu already
treats it so). If voice replication (ADR-052 follow-up) ships later, this same opt-in
storage covers the voice sample. GOV-008 gets a pointer to this exception.
