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

## How we'll know it worked

Same shape as REQ-023's test, one notch harder: a user finishes a call and can
**say one sentence out loud, tomorrow, that they could not say before** — and
comes back for a second call before the real interview. Not a score. Explicitly
**not** a score: a number turns rehearsal into judgment and kills the surface
(pre-mortem #4).

Counter-metric (the thing that must NOT happen): a first call that ends early,
gets interrupted mid-answer, or leaves nothing behind.

## Related

REQ-023 (Prep slice 1 — this is its deferred slice 2), REQ-025 (grounded
entry / real JD), ADR-026 (prep_sessions), ADR-028 (prep_kits — the kit becomes
this call's agenda), ADR-021/REQ-018 (defense hooks → the gap-defense deck),
ADR-027/ADR-029 (company outlook — the interviewer's employer context),
GOV-005 (practice ≠ cheat — binding, and the note that told us to write an ADR
against it before building this), GOV-001 (what already goes to Google),
`docs/research/RESEARCH-live-interview-practice.md` (the evidence),
product vision (candidate model as the central asset; Phase 2/3).
