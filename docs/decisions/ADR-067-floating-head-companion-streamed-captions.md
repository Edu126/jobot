# ADR-067: Floating-head companion + streamed captions in the voice runner

Date: 2026-09-28 (backfilled 2026-10-01)
Status: Accepted (look still under exploration — `static/avatar_lab.html`)
Relates to: ADR-052, ADR-054, commits 550550c, db09311

## Context
The canvas orb felt abstract. Captions arrived in chunks ahead of the voice, which broke the sense of a real call.

## Decision
- A floating-head companion (matte head, dark visor, glowing dots, no mouth) replaces the orb. It's driven by the real mic and coach analysers: thinking, speaking, listening, idle.
- The audio graph is unchanged: it still owns playback and echo-cancel routing.
- Coach captions stream at about 18 chars per second, paced to the audio.

## Alternatives considered
- A lip-synced avatar: uncanny, and costly.
- Keeping the orb: too abstract.

## Consequences
Canvas drawing must handle a 0-size start (ResizeObserver plus a radius clamp). The look is still open in the avatar lab.
