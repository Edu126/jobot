# RESEARCH-PLAN-live-interview-practice — should Prep gain a LIVE voice interview, and what is the model?

Date: 2026-09-16
Status: **Launched** 2026-09-16 (deep mode, 4 pillars).
Mode: deep
Feeds: REQ-041 (live prep call), ADR-047+ (transport / modes / avatar / cost
guard), GOV-008 (voice data), `docs/product/vision.md` (moat + Phase 2/3).

## The question

REQ-023 deferred "assessment practice" to Slice 2 and **blocked it on a
research pass** (Eduardo's explicit call). This is that pass, widened by
Eduardo 2026-09-16: not just *practice*, but a **live voice call with an AI
interviewer** (Gemini Live streaming) inside Prep — grounded on everything the
session already holds (company outlook, JD, résumé, gaps, STAR bank).

The decision it unblocks: **do we build the live call, in what mode framework,
at what cost ceiling, and on which transport** — or do we stay asynchronous?

## Pillars (4)

1. **Does verbal rehearsal actually work?** — evidence for interview
   training / behavioral rehearsal / mock interviews on interview performance,
   self-efficacy and anxiety; feedback timing (immediate vs. delayed);
   retrieval practice & testing effect; deliberate practice; speaking-aloud
   (production effect). Bounds: peer-reviewed, verifiable via OpenAlex/Crossref.
   *Defines whether the feature has a real mechanism or is theater.*
2. **Competitive landscape** — how existing products do AI interview practice
   (Google Interview Warmup, Yoodli, Final Round AI, Big Interview, Pramp /
   Exponent, HireVue practice, Huru, LinkedIn's coach) + **adjacent voice-AI
   pedagogy** worth borrowing (Duolingo roleplay, Speak, ELSA). For each:
   interaction model, feedback moment, session length, price, known failure
   modes. *Defines what to borrow and what not to re-learn.*
3. **Gemini Live technical envelope** — models + availability, transport
   (WebSocket vs WebRTC), ephemeral tokens (can the browser connect without
   proxying audio through our Fly box?), session duration + context limits,
   VAD / barge-in, input & output transcription, tool calling, and the
   **client-side avatar/lip-sync** path (Web Audio `AnalyserNode` amplitude →
   mouth) with zero server post-processing. *Defines what is buildable at $0
   ops on one small Fly machine.*
4. **Unit economics + business value** — real token/minute pricing for live
   audio, cost of a 5-minute call, cost ceiling per user/day, free-tier
   reality, competitor price anchors, and where the value lands in jobot's
   three-arc revenue model (episodic urgency vs. the continuous persona).
   *Defines whether this is a paid-tier anchor or a quota bomb.*

## Guardrails

- Model: **Sonnet** sub-agents, one per pillar, tightly scoped. No sprawl.
- Search primarily in English; regional sources only where distinct.
- Every citation **verified** (OpenAlex / Crossref) or explicitly flagged ⚠.
- Product/vendor claims (pricing, limits) must cite the **vendor's own docs**
  with a date — pricing drifts; an unverifiable number is flagged, not quoted.
- Credit budget: 4 pillar agents + consolidation done in-session (no 5th agent).
- Lateral thinking + Six Hats analysis is **founder-side** (Eduardo + Vision),
  not delegated — agents source, they don't conclude.

## Expected output

One `RESEARCH-live-interview-practice.md` memo with an Implications table
(every row ending in a REQ/ADR/GOV hook) + a decisions section, reviewed
high-level with Eduardo before anything becomes a REQ/ADR.
