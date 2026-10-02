# ADR-064: Practice starts on Setup's Start — no "Ready when you are" gate

Date: 2026-10-01 (backfilled same day)
Status: Accepted
Relates to: ADR-052, commit bab3780

## Context
The voice runner made you click "Ready when you are" after Setup, which was a second start button. Browsers only unlock the mic and audio on a user gesture.

## Decision
- Setup's **Start** requests the mic inside that click, then posts.
- The live page checks AudioContext on load. If it's running, it connects straight away behind a "Connecting…" orb. If it's still suspended (Safari, a reload, a direct link), it falls back to the tap gate.
- If the mic is denied, the error shows inline on Setup with no navigation.

## Alternatives considered
Always gating: safe, but it's one more click on every session.

## Consequences
Two code paths (auto and fallback) to keep working. Safari users still see the gate.
