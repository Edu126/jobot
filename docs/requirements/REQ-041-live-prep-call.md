# REQ-041: Prep gains a LIVE voice call with an AI interviewer

Date: 2026-09-16
Source: Eduardo (voice note, 2026-09-16)
Status: Open — research complete (`RESEARCH-live-interview-practice.md`);
decisions recorded in ADR-047…ADR-051 + GOV-008.

> This is **Cluster B, slice 2** — the "assessment practice" REQ-023 deferred
> and **explicitly blocked on a research pass first**. That pass is done; this
> REQ is its landing.

## What they asked for

In his words (2026-09-16, condensed from the voice note):

- *"dentro de la sección de preparación, las personas van a poder hacer una
  llamada con el AI"* — Prep gets a real-time voice call, not another text kit.
- *"unas secciones de preguntas… te presentas, behavioral, the skills, algo
  corto, no más de cinco minutos"* — short, sectioned, ≤5 minutes.
- *"el usuario va a poder tener opciones para seleccionar… no de complejidad,
  pero sí qué cosas en particular quisiera revisar"* — the user picks the
  **focus**, not a difficulty level.
- *"un estilo de framework"* with at least three shapes: **feedback inmediato**,
  **conversación completa y luego feedback**, and **estilo life coach**.
- *"practícalo repitiéndolo de manera verbal"* — the point is verbal production,
  not memorizing a text.
- *"ya tenemos información de la empresa, research, cultura, el job offer…
  cómo aglomerar toda esta información para tener una entrevista en vivo"* —
  grounded on everything the prep session already holds.
- *"estilo de una llamada en Zoom o Google"* with *"una animación que se va a
  render desde el lado del usuario"* — an avatar whose mouth moves with the
  audio waves, **rendered client-side**, *"para no estar haciendo mucho
  post-processing"*.
- Possibly *"tres tipos de entrevistadores… más como un estilo avatar"*, picked
  at random.
- And explicitly: research how others have done it, how we could fail, lateral
  thinking + the thinking-hats pass, **cost per call**, and the **business
  value** — not just "a feature".

## What they actually need

Prep today hands the candidate *text*: a company outlook, a STAR bank, reverse
questions. Text is where preparation **starts** and it is not where the
interview happens. The gap between "I read my STAR answer" and "I said it out
loud, to a stranger, under time pressure, in my second language" is the gap the
product exists to close — and it is precisely the gap a written kit cannot.

Three needs stack underneath the ask:

1. **Production, not recognition.** Reading a prepared answer trains
   recognition; saying it trains retrieval. The candidate who has *never said
   it aloud* discovers the sentence doesn't exist yet — at the real interview.
2. **Rehearsal under arousal.** The felt stakes of a live voice call are the
   active ingredient, not a side effect. But that cuts both ways: too much on
   the first contact and the user never comes back (see the pre-mortem).
3. **The candidate model gets richer by listening.** jobot's moat is a
   "narrated career self" (product vision, *the central asset*). Voice is the
   cheapest way a human will ever hand us their career narrative — ten minutes
   of speech beats an hour of form-filling. A live call is a Phase-3 data
   instrument arriving inside a Phase-1 moment.

And one constraint the ask carries in its own words — *"no más de cinco
minutos"*, *"sin mucho post-processing"* — is not a UX preference. It is the
cost model and the architecture, stated by the user before anyone measured it.

## The model — what we're actually proposing

**The kit is the script; the call is the stage.** `prep_kits.star_qa` already
holds the deck kinds Eduardo named, already grounded, already GOV-005-checked.
The live session doesn't invent an interview — it *conducts* one we already
generated. (ADR-048.)

**Two axes, no difficulty slider:**

| Axis | Options |
|---|---|
| **Stance** — who is on the other side | **Simulation** (default: no interruptions, ~5 min, debrief after) · **Drill** (interrupts with a short correction — the beginner's ramp) · *Mentor* (exploratory; **deferred**) |
| **Deck** — what gets asked | presentación (`why_you`) · behavioral · situational · culture fit · **defensa de gaps** (`defensive_gap`) |

Simulation is the default **because the evidence says so**, not by taste:
delayed feedback won 7 of 8 studies measuring retention ~a week out, and the
real interview *is* the delayed test. Eduardo's instinct led with
feedback-inmediato; the research moved it to second position, as the ramp.

**The shape of a call:**

1. Pick a stance + 1–3 decks → `POST /prep/{id}/call/token`. The server checks
   caps, builds the system instruction (company outlook × JD × résumé × the
   selected kit questions), mints a **short-lived ephemeral token**, logs the BI
   event, and steps out of the way.
2. The browser connects **straight to Gemini over WebSocket** — the audio never
   touches our Fly machine (ADR-047). `@google/genai` loads as a CDN ES module,
   so ADR-003's no-build-step rule survives.
3. **Audio-only.** The avatar is drawn client-side from the audio already
   playing (`AnalyserNode` → RMS → mouth). That is not a shortcut: the session
   cap is **15 min audio-only vs 2 min with video** (ADR-050). Eduardo's "solo
   una animación del lado del usuario" is what keeps the call legal.
4. The deck's N questions *are* the finish line — "no más de cinco minutos"
   enforced by content, not by a timer cutting someone off mid-sentence.
5. On hang-up the browser posts the transcript (streamed free, in-band, no STT
   hop). A second, ordinary `generate_json` call produces the **debrief**:
   strongest moment **quoted from their own words**, exactly *one* thing to
   change, what went unanswered, and where an answer met or missed a **specific
   JD requirement**. **Never a score** (ADR-049).

## Decisions — RESOLVED 2026-09-16 (post-research)

1. **Transport: browser↔Gemini directly, ephemeral token minted server-side.**
   Our box is sized for HTML fragments, not five minutes of PCM. ADR-047.
2. **Framework: stance × deck; Simulation is the default, Drill is the ramp,
   Mentor is deferred.** ADR-048.
3. **The debrief is a separate cheap call and carries no score.** ADR-049.
4. **Audio-only modality; stylized client-side avatar; one interviewer in v1;
   ES stays dark until `es-419` is confirmed.** ADR-050.
5. **Caps enforced at token-mint time; feature flag defaults OFF until the free
   tier is confirmed.** ADR-051.
6. **Voice + transcripts get their own governance note**, including the rule
   that "practice ≠ cheat" becomes *architecture* — no calendar hook, no
   live-call attach, no overlay, ever. **GOV-008.**

### Open gates (need a human, not an agent)

- **G1 — the $0 gate (blocking).** Whether the conversational Live model exists
  on the free tier, and the real $/1M audio rates. Both pages were egress-blocked
  from the research sandbox. If there's no free tier, this is the first jobot
  feature that costs money per use (~6¢ per 5-min call against a human coach's
  $75–225/h) — a product call, not an engineering one.
- **G2 — `es-419`.** If Google exposes only `es-ES`, shipping a Spanish call
  breaks non-negotiable #4.
- **D1 — does Drill ship in v1 at all**, or does v1 stay single-mode?

## How we'll know it worked

Same shape as REQ-023's test, one notch harder: a user finishes a call and can
**say one sentence out loud, tomorrow, that they could not say before** — and
comes back for a second call before the real interview. Not a score. Explicitly
**not** a score: a number turns rehearsal into judgment and kills the surface
(pre-mortem #4).

Counter-metric (the thing that must NOT happen): a first call that ends early,
gets interrupted mid-answer, or leaves nothing behind.

**One promise we will NOT make.** The strongest coaching study we found improved
interview performance and answer structure and **did not reduce interview
anxiety** — the authors flag anxiety as change-resistant. So the copy sells
*"you'll have the sentence"*, never *"you'll feel calm"*. Promising calm would
be exactly the sycophancy non-negotiable #1 bans, and the evidence doesn't
support it.

### Pre-mortem — how this fails (design against these)

1. **"El AI me interrumpió mientras pensaba."** VAD fires on a nervous pause →
   tune `silenceDurationMs` *slower* than a sales agent's (ADR-047).
2. **"Se cortó a los 4 minutos."** Session/socket caps mid-answer → audio-only
   lane + `sessionResumption` configured defensively.
3. **"Sonó a español de España."** Breaks non-negotiable #4 → gate G2.
4. **"Me dio un 7/10."** A score turns rehearsal into judgment → banned by
   ADR-049.
5. **"Me gasté la cuota del día."** One call starves scoring/kit → the ADR-029
   failure mode, re-run; caps at mint time (ADR-051).
6. **"Hice la llamada y no pasó nada."** No artifact = no value retained → the
   debrief and transcript persist (ADR-049).

## Related

REQ-023 (Prep slice 1 — this is its deferred slice 2), REQ-025 (grounded
entry / real JD), ADR-026 (prep_sessions), ADR-028 (prep_kits — the kit becomes
this call's agenda), ADR-021/REQ-018 (defense hooks → the gap-defense deck),
ADR-027/ADR-029 (company outlook — the interviewer's employer context),
GOV-005 (practice ≠ cheat — binding, and the note that told us to write an ADR
against it before building this), GOV-001 (what already goes to Google),
`docs/research/RESEARCH-live-interview-practice.md` (the evidence),
product vision (candidate model as the central asset; Phase 2/3).
