# RESEARCH — the live voice prep call (Prep slice 2)

Date: 2026-09-16
Status: Draft — pending high-level review with Eduardo (step 5 of the skill).
Feeds: REQ-041, ADR-047…ADR-051, GOV-008, `docs/product/vision.md`
Mode: deep (4 pillars)

> ⚠ **Read the verification note first.** The sandbox's network policy denies
> `api.openalex.org` and `api.crossref.org` (403 on CONNECT, confirmed from this
> shell and from the proxy's own failure log). The skill's DOI-API check could
> not be run. Every ✓ below means **cross-triangulated** (≥2 independent
> listings agreeing on title/authors/year/venue), which is a *weaker* standard.
> Several vendor pricing domains were also blocked, so **every price is
> third-party-triangulated and marked ⚠**. Verification debt is logged in
> `RESEARCH-PLAN-live-interview-practice.md`.

## TL;DR

1. **The mechanism is real, but it is not the one we assumed.** Structured
   interview coaching reliably improves *performance and answer structure*
   (Tross & Maurer 2008), and simulated interview training produces real job
   offers in RCTs (VR-JIT, Smith et al. 2014/2015). But the same study that
   found the performance gain found **no reduction in interview anxiety**. We
   should sell "you'll have the sentence" — never "you'll feel calm."
2. **The feedback-timing literature does not favor the interrupting mode.**
   Immediate feedback wins on same-session polish; delayed feedback won in 7 of
   8 studies measuring retention ~1 week out (Kulik & Kulik 1988). The real
   interview is *days away*, not minutes — which argues that the **debrief mode
   should be the default**, and the interrupting drill is the beginner's ramp.
3. **The white space is exactly where jobot already stands.** No competitor
   grounds practice in **JD + résumé + a known gap map** together; feedback in
   the category is about *delivery mechanics* (filler words, pace, eye contact),
   not answer substance; and **no product in the category serves LatAm Spanish**.
4. **The category's ethical failure is a live "copilot" during the real
   interview** (Final Round AI, with an anti-screen-share "Stealth Mode"). The
   backlash is already structural — Amazon banned it; Google and McKinsey
   reintroduced in-person rounds. GOV-005 must become *architecture*, not a
   promise: jobot should be structurally incapable of attaching to a live call.
5. **The kit is the script; the call is the stage.** Nothing here requires a new
   content engine — `prep_kits.star_qa` already carries the deck kinds Eduardo
   named, already grounded and GOV-005-checked.
6. **The architecture is cheaper than expected: the audio never touches our
   server.** The browser connects straight to Gemini over WebSocket using a
   **server-minted ephemeral token**; `@google/genai` loads from a CDN as an ES
   module, so ADR-003's no-build-step rule survives. Our Fly machine mints a
   token and gets out of the way.
7. **Audio-only is not a simplification — it is the constraint that makes a
   5-minute call possible.** Session cap is **15 min audio-only vs 2 min with
   video**. Drawing the avatar client-side from the audio we're already playing
   keeps us in the 15-minute lane. Eduardo's instinct was load-bearing.
8. **~6 cents per 5-minute call** (⚠ modelled from blocked pricing pages)
   against a human coach at $75–225/h. **But whether the Live model exists on
   the free tier could not be confirmed** — that single unknown decides whether
   this is a $0 feature or jobot's first paid-tier anchor.

## Findings

### Pillar 1 — Does verbal rehearsal actually work?

- **Job-search interventions raise employment odds ~2.67×** vs. control, and
  work best when they combine *skill-building* (incl. interview role-play) with
  *motivation/self-efficacy* work → Liu, Huang & Wang (2014), *Psychological
  Bulletin* 140(4):1009–1041 → "odds of obtaining employment were 2.67 times
  higher" → **high**.
- **Coaching improves interview ratings and answer organization** — three
  escalating coaching conditions, N=144 → Tross & Maurer (2008), *JOOP*
  81(4):589–605 → **high**.
- **…but coaching did NOT reduce interview anxiety** in that same study; the
  authors flag anxiety as change-resistant → Tross & Maurer (2008) → **med**
  (single study, directly on-topic). *This is the finding that edits our copy.*
- **Role-play specifically predicted better real structured-interview
  performance**, beyond job knowledge and motivation (N=213 field study) →
  Maurer, Solamon, Andrews & Troxtel (2001), *JAP* 86:709–717 → **high**.
- **Feedback's effect runs *through* self-efficacy**, not directly on outcomes
  (N=240 grads, simulated interview + timely feedback) → Petruzziello et al.
  (2021), *IJSA*, DOI 10.1111/ijsa.12334 → **med-high**.
- **Simulated interview training produces real job offers.** VR-JIT vs.
  treatment-as-usual improved live role-play performance (p=.046, ASD adults);
  a second RCT found trainees more likely to receive job offers (SMI adults),
  consistent across ~5 RCTs → Smith et al. (2014) *JADD* 44(10); Smith et al.
  (2015) *Psychiatric Services* 66(11):1173–1179 → **high** for those
  populations. **The closest analog that exists to what we're building.**
- **Retrieval beats restudy at delayed tests** even though restudy *feels*
  better and wins the 5-minute test → Roediger & Karpicke (2006), *Psych
  Science* 17(3):249–255 → **high**. Directly underwrites "say it, don't
  re-read it."
- **Production effect: ~10–20% memory gain for saying material aloud** vs.
  silent reading → MacLeod et al. (2010), *JEP:LMC*, PMID 20438265 →
  **med-high**, *but* the paradigm is single-word/list learning — extrapolating
  to multi-sentence spoken answers is an inferential leap, not a finding.
- **Feedback timing is unsettled and condition-dependent**: applied/classroom
  settings favor immediate; **7 of 8 studies with ~1-week retention windows
  favored delayed** → Kulik & Kulik (1988), *RER* 58(1):79–97 → **high** on the
  pattern, **med** on transfer to the interview domain.
- **"Timely" ≠ "instant"**; feedback quality depends on type and target level,
  and mistargeted feedback can be neutral or harmful → Shute (2008), *RER*
  78(1):153–189; Hattie & Timperley (2007), *RER* 77(1):81–112 → **high**.
- **The "over-rehearsal sounds canned" claim has NO peer-reviewed support**
  that the pillar could locate — practitioner blogs only → ⚠ **unverified**,
  **low**. *We were about to design against a folk belief.*

### Pillar 2 — Competitive landscape

| Product | Modality | Feedback moment | Grounded on JD+résumé? | Price (⚠ all third-party) |
|---|---|---|---|---|
| Google Interview Warmup | voice + transcript | post-answer | No — generic decks | free; **⚠ reportedly shut down Apr 2026** |
| Yoodli | video/voice roleplay (+ live-call overlay) | mostly post-session | No | free 5 lifetime → $8–20/mo ⚠ |
| Final Round AI | **live copilot during real interviews** + practice mode | live | ⚠ unconfirmed | ~$25/mo ⚠ |
| Big Interview | async recorded video + AI grading | post-session | No — question bank | $39/mo–$299 lifetime ⚠ |
| Pramp / Exponent | live **human** peer mocks | live + peer | No | free 5/mo + paid ⚠ |
| Huru | async AI voice, pulls real postings | post-session | **JD yes**, résumé no | $24.99/mo ⚠ |
| interviewing.io | live **human** senior engineers | live + write-up | No | $179+/session ⚠ |
| LinkedIn Premium prep | text Q&A from the actual posting | near-real-time tips | **JD yes** | ~$40/mo tier, limited beta ⚠ |

- **White space #1 — nobody grounds on JD + résumé + gap map together.** Huru
  and LinkedIn do JD-only; everyone else uses generic banks. jobot already holds
  all three, scored and cached. → **med-high**
- **White space #2 — the category is English-only.** No interview-practice
  product surfaced with LatAm-Spanish support; the only mature Spanish
  conversational-voice products are language-learning apps, which don't do
  interviews. Non-negotiable #4 stops being a constraint and becomes a moat. →
  **med**
- **White space #3 — feedback is about *delivery*, not *substance*.** Yoodli's
  own positioning concedes it measures "how you speak… not what you say."
  Scoring answer content against actual JD requirements is open. → **med-high**
- **White space #4 — no product ends a session in a durable artifact.** Every
  one ends in a private scorecard; none exports a revised bullet or updates a
  gap map. jobot's kit/résumé loop can close that circle. → **med**
- **Borrowable pattern — bounded, self-ending scenarios** (Speak's 3-task
  roleplays, Duolingo's scripted situations): a voice session needs a built-in
  finish line or it rambles and gets awkward. → **med**
- **Borrowable pattern — ~500 ms is the turn-taking cliff**; silence past it
  reads as "your turn," and 2–4 s breaks the illusion. Voice-agent teams mask
  model latency with acoustic fillers ("mmhmm", "let me check"). → **med-high**
  (convergent engineering sources, ⚠ not peer-reviewed)
- **Borrowable pattern — free tiers are volume-capped, not time-boxed** (5
  lifetime roleplays; 5 credits/month). A precedent for how to gate this. →
  **med**

**The ethical line (this is the important part).** Final Round AI transcribes a
*real, live* interview and injects suggested answers on screen in ~1–1.5 s, with
a "Stealth Mode" built to evade screen-share detection. Market response is
already structural: Amazon banned it; Google and McKinsey reintroduced in-person
rounds; an interviewing.io survey of 67 interviewers (52 at FAANG) found 81%
suspected AI-assisted cheating (⚠ single-source industry reporting). Yoodli
shows the gray middle — a legitimate coaching product that *also* ships a
live-call overlay. **The lesson: GOV-005's "practice ≠ cheat" must be enforced
by architecture, not policy.** No calendar hook, no live-call attach, no
overlay, no browser extension that can see another tab — ever.

### Pillar 3 — Gemini Live technical envelope

> ⚠ **Every ai.google.dev fact below is a search-engine snippet, not a direct
> fetch** — that domain is egress-blocked here too. One direct verification
> pass is required before code is written (see *Decisions*, gate G1).

- **Transport is WebSocket only.** No native WebRTC (partner bridges only —
  LiveKit, Pipecat, Twilio). ✓ (cross-confirmed)
- **The browser can connect DIRECTLY, with a server-minted ephemeral token.**
  That is the documented purpose of ephemeral tokens: no backend audio proxy.
  TTLs: **1 min** to *open* the session (`newSessionExpireTime`), **30 min**
  lifetime once running (`expireTime`). ⚠
  → *This is the decisive architectural fact.* The audio never touches our Fly
  machine; our server mints a token and stays out of the path. One tiny
  always-on box does not have to carry a media stream.
- **`@google/genai` loads from a CDN as an ES module** (`esm.sh` / jsDelivr) —
  **no bundler**, so ADR-003's no-build-step rule survives intact. ✓
- **Session caps: audio-only 15 min; audio + video 2 min** (without
  `contextWindowCompression`). ⚠
  → Our 5-minute call fits audio-only with room to spare — **and only because
  the avatar is drawn client-side from the audio we're already playing.** The
  moment we send video to Gemini, the cap drops to 2 minutes and the feature
  breaks. Eduardo's "solo una animación del lado del usuario" instinct is not a
  UI preference; it is what keeps the session legal.
- **The underlying WebSocket dies at ~10 min regardless**; `sessionResumption`
  bridges it (token valid 2 h). A 5-min call fits in one connection, but mobile
  backgrounding makes resumption worth handling defensively. ⚠
- **VAD is configurable**: `startOfSpeechSensitivity`, `endOfSpeechSensitivity`,
  `prefixPaddingMs`, `silenceDurationMs`; can be disabled for push-to-talk.
  Native-audio models handle barge-in. ⚠ (mechanism ✓, exact defaults ⚠)
  → Directly answers pre-mortem #1: a nervous candidate's mid-answer pause must
  not read as end-of-turn. We tune *slower* than a sales agent would.
- **Input AND output transcription stream in the same connection**
  (`inputAudioTranscription` / `outputAudioTranscription`) — a written record
  with **no separate STT hop and no extra cost**. ⚠
  → The post-call artifact is nearly free. This is what makes the debrief viable.
- **No clean "structured JSON at the end" mode.** A scorecard needs either live
  function-calling or **a second, ordinary `generateContent` call over the
  transcript** — i.e. a new llm-surface site on the normal cheap chain. ⚠
- **30 HD voices, 24 languages**, settable per session (`voice_name`,
  `language_code`). Multiple interviewer personas are trivial. ⚠
  **`es-419` (LatAm Spanish) could NOT be confirmed** in Google's own table —
  only general Spanish / `es-ES`. ⚠ **Blocking check for non-negotiable #4.**
- **Audio formats:** input 16 kHz 16-bit PCM mono; output 24 kHz. ⚠
- **Client-side lip-sync needs no library at all**: Web Audio `AnalyserNode` on
  the playing node → RMS envelope per animation frame → mouth scale. For real
  visemes, **wawa-lipsync** (MIT, browser-native) or **TalkingHead.js**. ✓
  **Rhubarb is an offline desktop tool over finished files — unusable here.** ✓
- **Free-tier status of the conversational Live model: NOT CONFIRMED either
  way.** ⚠ *The single most important unknown in this memo.*

### Pillar 4 — Unit economics & business value

> ⚠ Pricing pages were egress-blocked; every figure is triangulated from
> snippets. Treat as a bearing, not a coordinate.

**The arithmetic** (Gemini Live native audio: $3.00/1M input audio tok,
$12.00/1M output audio tok, 32 tok/s in, 25 tok/s out; 50/50 speaking split;
~6k text tokens of JD + résumé in the system instruction at $0.50/1M):

- input: 30 s × 32 tok/s = 960 tok/min → **$0.00288/min**
- output: 30 s × 25 tok/s = 750 tok/min → **$0.00900/min**
- context, once per session: 6,000 × $0.50/1M = **$0.0030**

| Call | Expected | With ×1.5 buffer* |
|---|---|---|
| 5 min | **$0.062** | ~$0.09 |
| 10 min | $0.122 | ~$0.18 |
| 15 min | $0.181 | ~$0.27 |

\* the buffer is *our own* assumption (silence is reportedly still tokenized),
not a vendor figure.

- **A 5-minute call costs about six cents.** ⚠
- **Price anchors:** human interview coach **$75–225/h** (exec $220–550/h);
  Yoodli $8–28/mo; Big Interview $39/mo; Final Round AI ~$25/mo annual;
  Google Interview Warmup free — **and reportedly shut down**. ⚠
- **A per-user cap of 3–5 calls/day bounds worst-case exposure under
  $1/user/day** at these rates — a far cheaper control than policing session
  length. ⚠
- **Cascaded STT→LLM→TTS runs $0.007–0.029/conversation-minute** vs ~$0.091/min
  for OpenAI's native audio — but our computed Gemini blended rate (~$0.012/min)
  **is already inside the cascaded band**. The usual "cascade to save money"
  reflex does not obviously apply. ⚠
- **OpenAI Realtime is ~10× our modelled Gemini rate** ($32/$64 per 1M) — the
  BATNA is real but expensive. ⚠
- Market signals: AI-career-coach market $6.69B→$14.82B by 2030 (⚠ vendor
  marketing research); interview-coaching usage 23%→45% in a year (⚠); **but
  two-thirds of graduates offered free coaching didn't use it** (⚠) — adoption
  friction is the risk, not cost.
- **No direct data on what job seekers say they'd pay** was found. Gap.

## Tensions / open questions

- **Immediate vs. delayed feedback has no clean winner**, and our two headline
  modes sit on opposite sides of it. The literature suggests they optimize
  *different things*: Drill → same-session polish; Simulation+debrief → transfer
  to the real interview days later. That is a reason to ship both — but to
  **default to the debrief**, since the real interview is the delayed test.
- **Rehearsal ≠ calm.** Performance improves; anxiety may not. Any copy
  promising "practice until you're not nervous" is unsupported by the evidence
  we found, and is exactly the sycophancy non-negotiable #1 bans.
- **The production effect is lab evidence.** It underwrites our thesis
  directionally, not conclusively. jobot can generate the missing evidence.
- **The authenticity cost of over-rehearsal is folk belief.** We should *test*
  it (rehearsal reps vs. perceived naturalness), not design around it.
- **Pricing in this memo is unverifiable from here.** Treat every number as a
  bearing, not a coordinate.

## Implications for jobot

| Finding | So what for jobot | Action hook |
|---|---|---|
| Coaching lifts performance, not anxiety (Tross & Maurer) | Copy promises a *sentence you can say*, never calm. Ban "feel confident" framing | REQ-041 success test; ADR-049 |
| Delayed feedback wins the ~1-week retention test | **Simulation + debrief is the default mode**; Drill is the ramp, not the hero | ADR-048 (mode framework) |
| Feedback works *through* self-efficacy | Debrief leads with what they actually said well, sourced to their own words | ADR-049 (debrief contract) |
| VR-JIT RCTs → real job offers | The mechanism has precedent; measure transfer, not satisfaction | REQ-041 counter-metric |
| Retrieval > restudy; production effect | The call must make them **speak first**, before showing any model answer | ADR-048 |
| Nobody grounds on JD + résumé + gaps | Our grounding *is* the differentiator — surface it in-call like the kit's "grounded on" layers | ADR-047 |
| Category is English-only | LatAm-ES voice is a wedge; verify voice register before shipping ES | ADR-050 (voice/lang) |
| Feedback is delivery-only elsewhere | Score *substance vs. JD requirements*; delivery metrics are secondary | ADR-049 |
| No one ends in a durable artifact | The call must end in something that edits the kit / résumé | ADR-049 |
| Live "copilot" is the category's ethical failure | Make the attach **architecturally impossible**; write it down before building | **GOV-008** |
| ~500 ms turn-taking cliff; nervous pauses | VAD must be tuned *slower* than a sales agent's — a thinking candidate is not a finished turn | ADR-047 |
| Bounded scenarios keep voice sessions from rambling | Fixed deck of N questions = built-in finish line; matches "no más de 5 minutos" | ADR-048 |
| Ephemeral tokens let the browser connect directly | Audio bypasses the Fly box entirely; server only mints tokens. No media infra, no CPU cost | **ADR-047** |
| `@google/genai` loads as CDN ESM | No build step needed — ADR-003 holds | ADR-047 |
| 15 min audio-only vs **2 min** with video | Never send video to Gemini; avatar is drawn from played audio only | **ADR-050** |
| In-stream input+output transcription | The written artifact is free; no STT hop | ADR-049 |
| No structured JSON from a Live session | Debrief = a second ordinary `generate_json` call on the cheap chain → new llm-surface site | ADR-049 |
| Configurable `silenceDurationMs` / VAD sensitivity | Tune *slower* than a sales agent: a thinking pause is not a finished turn | ADR-047 |
| `es-419` unconfirmed in Google's language table | ES stays dark until verified — shipping Spain register breaks non-negotiable #4 | **ADR-050**, gate G2 |
| ~$0.06 per 5-min call; caps beat length-policing | Per-user daily call cap + hard session cap, enforced *before* the token is minted | **ADR-051** |
| Free-tier status of the Live model unconfirmed | Ship behind a flag that defaults OFF until verified | ADR-051, gate G1 |
| Live "copilot" backlash is structural (bans, in-person rounds) | No calendar hook, no live-call attach, no overlay — *ever*, by architecture | **GOV-008** |

## Decisions to make here (with Eduardo)

**G1 — the $0 gate (blocking, not delegable).** Two numbers decide whether this
ships on the current budget, and both are egress-blocked from here: (a) is the
**conversational Live model available on the free tier**, and at what rate
limit; (b) the real **$/1M audio token** row. Open
`ai.google.dev/gemini-api/docs/pricing` + AI Studio → Quotas in a browser and
eyeball them. If there is no free tier, this is the **first feature in jobot's
history that costs money per use** — which is a product decision (a paid tier
anchor), not an engineering one. Everything below is designed so that answer
changes a flag, not the architecture.

**G2 — `es-419`.** If Google exposes only `es-ES`, a Spanish call ships in
Spain register and **violates non-negotiable #4**. Verify before enabling ES;
until verified, ES stays dark rather than shipping wrong. (ADR-050.)

**D1 — Which mode ships first?** The evidence says default to
**Simulation + debrief** (the real interview is the delayed test). Eduardo's
instinct led with feedback-inmediato. Recommendation: ship **Simulation first**,
Drill second as the beginner ramp — but this is his call.

**D2 — Does the Mentor mode ship at all in v1?** It is the moat-acquisition
mode (narrated career self) and the weakest felt value. Recommendation: **not
in v1** — it needs an artifact to land in, and v1 has enough surface area.

**D3 — Interviewer personas: one or three?** Three voices is a `voice_name`
string, technically free. The cost is copy, testing and the uncanny-valley
risk. Recommendation: **one warm, neutral interviewer in v1**; personas after
we know people finish a call.

## Sources

### Pillar 1 (✓ = cross-triangulated, **not** DOI-API verified — see note)
- Liu, Huang & Wang (2014), *Psychological Bulletin* 140(4):1009–1041 — ✓
- Tross & Maurer (2008), *JOOP* 81(4):589–605 — ✓
- Maurer, Solamon, Andrews & Troxtel (2001), *JAP* 86:709–717 — ✓
- Maurer (2008), *JOB*, DOI 10.1002/job.512 — ✓
- Petruzziello et al. (2021), *IJSA*, DOI 10.1111/ijsa.12334 — ✓
- Caplan, Vinokur, Price & van Ryn (1989), *JAP* (JOBS program) — ✓
- Kulik & Kulik (1988), *RER* 58(1):79–97, DOI 10.3102/00346543058001079 — ✓
- Shute (2008), *RER* 78(1):153–189, DOI 10.3102/0034654307313795 — ✓
- Hattie & Timperley (2007), *RER* 77(1):81–112, DOI 10.3102/003465430298487 — ✓
- Roediger & Karpicke (2006), *Psychological Science* 17(3):249–255 — ✓
- MacLeod et al. (2010), *JEP:LMC*, PMID 20438265 — ✓
- Smith et al. (2014), *JADD* 44(10), PMID 24803366 — ✓
- Smith et al. (2015), *Psychiatric Services* 66(11):1173–1179 — ✓
- Smith et al. (2023), *Psychiatric Services*, DOI 10.1176/appi.ps.202100516 — ✓
- "Over-rehearsal sounds canned" — HR advice blogs only — ⚠ **not science**

### Pillar 2 (all vendor pricing ⚠ third-party; vendor domains egress-blocked)
- Duolingo investor filing (retention figures) — ✓ primary filed document
- CHI 2025, LLM voice agents / turn-taking — ACM DL listing — ✓ venue-listed
- G2 · aceround · four-leaf.ai · lastroundai · fabrichq · lodely · picovoice —
  product/pricing/latency triangulation — ⚠
- ACLU/EPIC FTC complaints re HireVue (employer-side context only) — ⚠ secondhand

### Pillar 3 (ai.google.dev egress-blocked — snippets, not direct fetches)
- ai.google.dev/gemini-api/docs/live-api, /capabilities, /ephemeral-tokens,
  /live-session, /live-transcribe, /pricing — ⚠ **snippet-sourced, unverified**
- cloud.google.com/blog — native-audio GA on Vertex AI — ✓ fetched directly
- github.com/google-gemini/gemini-skills — model IDs, audio formats, VAD config
  (official Google org, not the primary docs domain) — ⚠
- github.com/google-gemini/live-api-web-console — a browser↔WebSocket reference
  client exists — ✓
- jsdelivr.com/package/npm/@google/genai · esm.sh — CDN/no-bundler import — ✓
- github.com/wass08/wawa-lipsync (MIT, browser-native) ·
  github.com/met4citizen/TalkingHead · github.com/wzpan/rhubarb-lip-sync
  (confirms Rhubarb is offline-only) — ✓

### Pillar 4 (vendor pricing pages egress-blocked)
- ai.google.dev/gemini-api/docs/pricing — $3/$12 per 1M audio, 32/25 tok/s — ⚠
- platform.openai.com/docs/pricing — Realtime $32/$64 per 1M — ⚠
- yoodli.ai/pricing · biginterview.com/pricing/personal ·
  finalroundai.com/blog/final-round-ai-pricing — ✓ snippet-corroborated
- Thervo / Noomii / Talkspresso — human coach hourly rates — ⚠ aggregators
- inworld.ai voice-agent cost model — cascaded vs native $/min — ⚠
- Research and Markets / Business Research Company — market sizing — ⚠
  **vendor marketing research, not peer-reviewed**
