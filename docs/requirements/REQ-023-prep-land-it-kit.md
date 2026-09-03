# REQ-023: Prep — the land-it kit (Cluster B, slice 1)

Date: 2026-09-03
Source: Eduardo (product architect)
Status: Open — scoped this session; product decisions RESOLVED below.

> First **Cluster B** slice of the post-apply "land it" stage (REQ-017).
> Cluster A (gap enhancement / profile) shipped 2026-09-02; this opens the
> interview-readiness surface. Follows the solution-architecture practice
> (capture ask + need before building).

## What they asked for

In his words (2026-09-03): *"vamos a trabajar en el tab de Prep"* — the
post-callback surface from REQ-017's Cluster B. Over the shaping session he
fixed: start Prep now (conscious sequencing jump), a dedicated **Prep** tab,
entry via a *"Prep from here"* button on the expanded job result and via
**marking a job as applied**, plus **link/paste** for interviews that didn't
come through jobot (*"a veces es difícil encontrar la vacante específica a
través del dropdown"*). Slice 1 = company outlook + likely questions with
grounded answers + questions to ask; assessment practice deferred to a later
slice that *needs its own research first*.

## What they actually need

jobot's funnel help ends at `apply`, but landing is the goal. At a callback
the candidate hits a **second blank-page cliff** — what do I say, is this
company even good, how do I prep — the exact high-cognitive-load surface the
product vision exists to carry. Answering novel questions in the candidate's
own voice ("why you?", culture/situational fit) is the sharpest expression of
the **candidate-model moat** (product vision, "the central asset"). This is
deeply on-vision for the moat; the tension is **sequencing** (below), which
Eduardo accepted.

## Product decisions — RESOLVED 2026-09-03 (Eduardo)

1. **Name = Prep (EN) / Preparación (ES).** The activity, neutral, scales if
   the kit grows. Register matches the nav (Jobs · Journey · Prep · Profile /
   Empleos · Trayecto · Preparación · Perfil).
2. **IA = dedicated top-level tab; the unit is the VACANCY, not the
   application record.** Revised 2026-09-03 after Eduardo flagged the
   apply→callback time gap (a callback can land *months* later, unpredictably).
   Auto-populating Prep from every "applied" job = a large, stale, low-signal
   list. Instead:
   - Prep lists **prep sessions the user actively created** (few, high-signal),
     each a per-vacancy workspace.
   - **Creating a prep session IS the callback signal** — no separate event
     needed; the act of prepping = "this one advanced" (BI loop closed for
     free, decision 4).
   - **Journey reconciliation dissolves.** Prep is *not* a second applications
     board. A session *references* an application when matched, but does not
     depend on application state. Journey stays the tracker; they don't
     compete. (Supersedes the earlier "application state = single source of
     truth" framing.)
3. **Entry = identify the vacancy, with graceful degradation** by how much we
   have stored (revised 2026-09-03):
   1. **"Prep from here"** button on the expanded job result (fresh in jobot)
      → reuse stored JD + score + matched/gaps + defense hooks. Zero re-entry.
   2. **Paste the link** → normalized-URL match against stored jobs. Match →
      same as (1). No match → (3).
   3. **Paste text** (JD or role+company) → matched against our DB (see
      *Matching strategy*), else work fresh.

   *Dropped:* the earlier "mark-as-applied surfaces it in Prep" idea — apply and
   callback are different moments; marking applied belongs to Journey. Prep is
   created at the callback moment.

## Matching strategy — finding the vacancy in our DB

Search space is **not** the whole jobs DB — it's the **tailored-jobs set
first** (`tailor_runs`), then scored jobs. Rationale: the tailor set is small
(cheap, deterministic, no LLM), tailoring is the **strongest "I applied here"
signal** we have, and it holds the **richest reuse** — tailored résumé, score,
matched/gaps, defense hooks. (Note: company outlook is **not** cached today —
`fetch_company_context` re-runs each Tailor opt-in; ADR-027 adds the shared
`company_outlook` cache so a matched job's outlook can be reused, not just
re-fetched.)

Ladder (most→least precise): **exact link/URL → tailored set (company+title,
then JD text fuzzy-ratio) → scored set → fresh.** Fuzzy = rapidfuzz-style
string similarity, **no embeddings, no LLM** (embeddings = infra/cost off the
$0 POC).

Honesty guardrail (grounding, non-negotiable #1): **propose, don't auto-bind.**
Only an exact URL match auto-binds. Otherwise surface the **top 2–3 candidates
for a one-tap confirm** (*"¿Es esta? [Job A · Company] [Job B] [Ninguna]"*).
This also **kills the "dropdown is hard" friction** — we propose the few likely
matches instead of asking the user to search everything. Binding to the wrong
vacancy would ground the entire kit on the wrong JD, so a low-confidence match
must never bind silently.
4. **Sequencing jump ACCEPTED.** REQ-017 recommended leading Cluster A; we
   lead the moat now instead. Cost of the jump is paid by (2) below — the MVP
   **instruments the callback/interview signal**, so the surface has a trigger
   and the BI loop stays whole (vision non-negotiable #5).
5. **GOV-005 binds unchanged.** Company/employer outlook is explicitly
   candidate-side and allowed; likely-questions answers are grounded in TRUE
   candidate data (reuse REQ-018 defense hooks — the "relocate defense-hook
   material into an interview-prep surface" decision noted in REQ-017 lands
   here); nothing supplies live assessment answers.

## MVP scope

**Slice 1 (this REQ):**
- **Company outlook** — reuse `core/llm/company_research.py` (Google Search
  grounded briefing + candidate-side risk/outlook). GOV-permitted, high reuse.
- **Likely questions + grounded answer** — the moat: "why you?", culture /
  situational fit, in the candidate's voice, grounded on `company × candidate`.
  Reuses REQ-018 defense hooks for real-gap questions.
- **Questions to ask (candidate → employer)** — thin, cheap, low GOV risk.
- **Vacancy matching + confirm** — the entry ladder above; creating the session
  is itself the callback signal (no separate event to instrument).

**Deferred to Slice 2 (own REQ):**
- **Assessment practice** (behavioral / logical / problem-solving). Highest
  GOV-005 risk (practice ≠ cheat). **Blocked on a research pass first** —
  Eduardo's explicit call.

**Fast-follow (own governance note):**
- **Link-as-fetch.** Link-as-*identifier* (URL match against our stored jobs)
  ships in the MVP — no new hop, we already hold the JD. Link-as-*fetch*
  (parsing a URL we've never seen) is an arbitrary job-URL fetch hop, gated by
  **GOV-006** (SSRF blocks + injection fencing mandatory before ship; same
  precedent that kept LinkedIn eval on paste, REQ-017 decision (c)). Note:
  months later the live posting may 404 — our stored JD is more reliable than
  re-fetching, another reason match-first.

## Contract-layer notes (non-negotiables)

- Grounded-or-none (ADR-005): a kit section either passes its grounding check
  or doesn't render — no "Regenerate" escape hatch (vision non-negotiable #2).
- Cache-key **all dimensions**: company × role × candidate(résumé hash) ×
  lang (ADR-008 rule 3, [[feedback_cache_key_all_dimensions]]). Lazy.
- LatAm-first ES via `language_instruction("es")` (non-negotiable #4).
- New Gemini call sites get logged in `docs/architecture/llm-surface.md`
  (ADR-008 hard rule).

## How we'll know it worked

The thing that stops happening: a candidate with an interview scheduled
staring at a blank page. Success = a user opens Prep for a specific interview
and leaves with at least one concrete thing they'll say — reads the outlook,
or drafts/edits one grounded answer — not a number on a dashboard.

## Related

REQ-017 (land-it stage umbrella; this is its first Cluster B slice),
REQ-018 (gap enhancement / defense hooks — reused here), REQ-019 (aggregated
gap map), GOV-005 (enhance ≠ fabricate; practice ≠ cheat; employer risk
allowed — binding), GOV-003 (candidate alignment), product vision
(candidate-model moat; gap monetized 3×), `docs/product/milestones.md`
(Phase 0 instrumentation), `core/llm/company_research.py` (existing block).
**ADR-026** (prep_sessions self-contained per-vacancy model + matching),
**ADR-027** (company outlook: persistent shared cache + structured two-hop +
sanctioned news-refresh), **ADR-028** (prep_kits read-only cached blob — STAR
Q&A bank incl. defense-hook reuse + reverse questions; copy-first, no Q&A
regenerate). **GOV-006** (link-as-fetch SSRF/injection gate — fast-follow). UI reference:
designer mockup 2026-09-03 (context bar · 3-facet intel · STAR bank · reverse
interviewing).
