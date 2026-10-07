# ADR-070: Speaking time is measured from the recorded audio, server-side

Date: 2026-10-06
Status: Accepted
Relates to: REQ-042, REQ-043, ADR-048

## Context
The pace gauge divides words by speaking seconds. The browser counted those seconds only while the smoothed mic level was above a fixed 0.02. With the browser's AGC and noise suppression, a quiet mic never crossed it: session 39 had 106 words, 0 s and no gauge, and the mic meter looked dead. When the level did cross 0.02, soft speech went uncounted, so the seconds came out short and wpm too high (session 40: 192 wpm "fast").

## Decision
The server measures speaking time from the candidate WAV it already receives (`audio_metrics.speaking_seconds`). Voiced frames are compared against that recording's own noise floor, and gaps under 1 s are bridged so the result matches speaking-rate norms. The browser count is kept only as a fallback. The browser gate and meter now adapt to each mic's noise floor too.

## Alternatives considered
- Lower the fixed browser threshold: fixes one mic and breaks another.
- Ask the model for the duration: violates REQ-042 (numbers come from code).

## Consequences
Old sessions can't be recomputed (audio isn't kept, GOV-008). The 1 s bridge is a judgement call: long thinking pauses mid-answer don't count as speaking.
