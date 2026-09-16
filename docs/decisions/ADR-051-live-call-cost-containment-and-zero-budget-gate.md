# ADR-051: The live call is capped before the token is minted, and ships behind a flag that defaults OFF until the free tier is confirmed

Date: 2026-09-16
Status: Accepted (design) — **implementation blocked on gate G1**
Relates to: REQ-041, ADR-047 (token minting is the enforcement point), ADR-004
(free tier + fallback chain), ADR-019 (cache as stability), `core/llm/usage.py`
(per-identity daily cap), `docs/rate-limiting-quotas.md`, research memo Pillar 4

## Context

Every Gemini call in jobot today is **short, cached, and free**. A live audio
session is none of those things: it is metered per second, it cannot be cached,
and it is the first call site whose cost scales with *how long the user feels
like talking*.

Pillar 4's arithmetic (⚠ modelled from egress-blocked pricing pages): native
audio at $3/1M input and $12/1M output tokens, 32/25 tokens per audio-second,
50/50 speaking split → **~$0.062 for a 5-minute call**, ~$0.09 with a buffer for
tokenized silence. A per-user cap of 3–5 calls/day bounds exposure **under
$1/user/day**.

And the decisive unknown: **whether the conversational Live model exists on the
free tier at all could not be confirmed.** Pillar 3 and Pillar 4 both hit the
same wall.

## Decision

**1. The gate.** The feature ships behind `LIVE_PREP_ENABLED`, **defaulting
OFF**, until someone opens `ai.google.dev/gemini-api/docs/pricing` + AI Studio →
Quotas in a browser and confirms (a) free-tier availability and rate limits, and
(b) the real audio token prices. This is gate **G1**. If there is no free tier,
this becomes **the first feature in jobot's history that costs money per use** —
a product decision (a paid-tier anchor), not an engineering one, and it belongs
to Eduardo.

**2. Caps are enforced at token-mint time, never mid-stream — and "enforced"
means bound into the token, not passed beside it.**

*Rewritten 2026-09-16 after adversarial review, which broke the first draft.*
The original said caps were "enforced at mint time… a hard session cap **passed
in** the session config". That was wrong in a way worth naming: **the client
sends the setup frame.** A cap we merely hand to the client is a cap the client
can ignore — and ADR-047 is explicitly built so we never look again. So:

- **The caps hold only if the token is config-locked** (ADR-047's
  `live_connect_constraints` clause). **Gate G3.** If tokens cannot bind model,
  system instruction, modality, tools and duration, then nothing in this ADR is
  enforceable and the feature needs a different transport — not a stricter
  sentence.
- **There is no implementation path today, and the obvious shortcut is a trap.**
  `core/llm/usage.py::check_and_charge` keeps **one aggregate bucket** keyed
  `(identity, "any", day)` at `MAX_LLM_CALLS_PER_DAY = 600`; a live call would
  count as 1 of 600, the same as a free JSON score. Special-casing the model
  inside that aggregate would let ~200× the modelled dollar exposure through
  before the aggregate noticed. A live-call cap needs **its own counter**
  (`live_call_usage(identity, day, calls)`) plus a real concurrency row — new
  schema, not a flag on old code.
- **The identity these caps key on is trivially rotatable.**
  `ui_web/ratelimit.py::get_identity` prefers the `jobot_sid` cookie; a private
  window mints a fresh one and a fresh bucket. `docs/rate-limiting-quotas.md` §9
  already says it: *"Don't rate-limit by session cookie alone. Attackers rotate
  cookies for free."* For a surface metered in real money this must key on
  something not casually rotatable — `resume_hash` ownership now, the account
  once auth exists — or the budget must be sized assuming the bypass.
- **Whose money is at risk:** each beta user supplies **their own**
  `GOOGLE_API_KEY` to their own Fly app (GOV-001). A runaway session burns *that
  user's* quota — the same person the feature is for. That is not a reason to
  relax; it is the reason the cap is a kindness, not a business control.

With those preconditions stated, the caps themselves:
- **per-user daily call cap** (start: 3/day, in its own counter) — cheaper and
  kinder than policing session length;
- **a hard session cap bound into the token** (5 min for Simulation), well
  inside the ⚠ reported 15-minute audio-only limit;
- **`response_modalities: ["AUDIO"]` and an empty tools array, both locked** —
  so a stolen or replayed token cannot become a general-purpose voice+tools
  Gemini session on the user's key;
- **one concurrent call per user** — concurrency, not RPM, is the right control
  for long-lived sessions;
- the existing `check_and_charge` identity accounting is extended to count a
  live call as its own unit, so a call **cannot silently eat the quota that
  scoring and the kit depend on** (the ADR-029 failure mode: one surface
  starving another).

**3. The kill switch already exists and must cover this.** `LLM_DISABLED=1`
short-circuits every site (`feature_flags.is_llm_disabled()`); the mint endpoint
checks it **before** minting, not after.

**4. Cost is never a user-facing dial.** No "minutes remaining" meter, no
upgrade nag mid-call (non-negotiable #2). When the cap is reached, the entry
point says plainly that today's calls are done — the same honesty posture as an
empty kit.

## Alternatives considered

- **Cut the session mid-stream when it runs long.** Rejected: we cannot observe
  the stream (ADR-047), and severing someone mid-answer is the worst possible
  failure for a surface whose entire job is making them feel prepared. Bound the
  *content* (ADR-048's fixed deck) and the *count*, not the seconds.
- **Meter and bill per second.** Rejected: no billing surface exists, and it
  would make the emotional-stakes surface the first paywall.
- **Cascaded STT→LLM→TTS to cut cost.** Rejected in ADR-047 — at our modelled
  rate native audio is already inside the cascaded price band.
- **Ship it on and watch the bill.** Rejected: an unbounded per-second cost on a
  free-tier account with no billing alerts is how a $0 project stops being one.
- **Wait for the free tier to be confirmed before designing.** Rejected — that
  is what the flag is *for*: the answer changes a boolean, not the architecture.

## Consequences

- **The feature can be fully built and tested on -edu while the flag is off.**
  Nothing about G1's answer changes the transport, the schema, or the modes.
- If the free tier excludes Live, jobot faces its first real "this feature costs
  money" conversation — with unusually good numbers to have it with (~6¢ against
  a human coach's $75–225/hour).
- A daily cap of 3 is a guess. It is instrumented from day one so it becomes a
  measurement rather than a guess.
- **A crashed or backgrounded tab still spends a slot** (we charge at mint), with
  no debrief to show for it and no "calls remaining" meter to explain the
  refusal (non-negotiable #2). That is an accepted unfairness, and a
  `live_call.abandoned` event exists so we can see how often it bites.
- Live calls are **uncacheable by nature** — the first call site that breaks
  ADR-019's "cache is stability" pattern. Reproducibility moves from the cache to
  the *agenda*: the same kit yields the same questions (ADR-048), even though the
  conversation differs.
