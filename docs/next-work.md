# Next work — open items

**State as of 2026-09-08.** Scoring v2 is **LIVE**, not pending. The
coverage-anchored 0-100 ([ADR-018](decisions/ADR-018-bucketed-scoring-engine-rank-then-judge.md))
+ cache stability ([ADR-019](decisions/ADR-019-gemini-scoring-nondeterministic-stability-via-cache.md))
+ cross-language judge ([ADR-017](decisions/ADR-017-jd-language-source-of-truth.md))
shipped and merged to `main` (`semantic_score.py`, `PROMPT_VERSION = 2026-08-31-coverage-crosslang`).
The `claude/sprint-7-scoring-rework` branch is merged and deleted. Bucket-only
display ([ADR-016](decisions/ADR-016-bucketed-fit-display.md)) was superseded by
[ADR-038](decisions/ADR-038-keep-numeric-coverage-score-verdict-tinted.md) — we
keep the numeric coverage score in a verdict-tinted ring. The A-layer
(`lite_score.py`) is intentionally unwired ([ADR-020](decisions/ADR-020-defer-lite-score-a-layer.md)).

## Actually open

1. **REQ-016 sprint hygiene** (deferred by Eduardo 2026-08-31). `/simplify` +
   `/code-review low` on the REQ-016 commits (`e630742` B-layer, `d01a305`
   validation harness + A-layer rollback) — to be folded into a larger
   project-wide review.
2. **Minor deferred** (2026-08-26 close-out): real anonymized résumé fixtures;
   a DB-path-injection param for `ai_summary` so the stale-cache fix gets a test.

_Closed 2026-09-01: the cross-language prompt go/no-go (`data/ab_scoring_2026-08-31.md`).
Eduardo decided not to run the HITL validation — REQ-016 ships as-is on trust.
That sheet + the HITL method stays on file if scoring quality is ever doubted._

---

_Everything below is dated history, kept for the reasoning trail._

## 2026-08-31 — Cache/memory architecture map + Mehran resume-gen feedback (MAP ONLY, do not fix yet)

Opened by Eduardo. Suspicion: "part of the cache stays in RAM, not DB."
**Confirmed — yes.** Audit of where state lives:

**In-RAM (module-level, lost on process death):**
- `core/llm/gemini.py` — `_exhausted_models` (model→quota-exhaustion date) and
  `_request_counts` ((model,date)→count). Comment acknowledges "cleared on
  restart."
- `core/settings.py` — `_cache` dict. **Write-through to DB**, repopulates on
  miss → lower risk.
- `core/jobs/ats/oracle_hcm.py` — `_SITE_COMPANY_CACHE` scrape optimisation.
  Minor.

**Durable (DB/file — already migrated, safe):** task state (`core/jobs/tasks.py`,
PR-2 migration off the old in-memory `ui_web.state.search_tasks`), job-search
cache (`data/jobs_cache/*.json`), scores / suggestions / ai_summary (SQLite).

**Risk of keeping the RAM state, esp. on Fly `auto_stop_machines='stop'`:**
The machine cycles often → `_exhausted_models` + `_request_counts` reset every
cycle. Effects: (a) re-probe exhausted models → wasted 429s; (b) the fallback
chain can pick a *different model* across runs → **inconsistent model →
inconsistent scores/quality**; (c) request-count shown to the user is wrong
after any restart; (d) if ever scaled >1 machine, per-process RAM state never
shares → divergence.

**Mehran feedback (search-by-link, LinkedIn job 4454079380, aggressive resume gen):**
1. *3 aggressive attempts → totally different scores each.* Mapped root causes:
   (a) scoring `temperature = 0.4` in `core/llm/gemini.py` → inherent run-to-run
   LLM non-determinism; (b) probable model-fallback divergence from the RAM-reset
   exhaustion state landing different runs on different models. This is exactly
   what [REQ-015](requirements/REQ-015-deterministic-scoring-redesign.md) /
   [REQ-016](requirements/REQ-016-scoring-v2-rank-aware-honest-fit.md) target.
2. *First aggressive run truncated the resume's experience.* Separate from cache
   — a generation/writer truncation bug (candidates: `MAX_RESUME_CHARS`,
   `core/resume/ai_regenerate.py`, `core/resume/writer.py`). Same class as the
   "mid-word evidence truncation" already fixed once in Sprint 7 hygiene.

**Improvement options:**
- ~~Persist gemini exhaustion + request counts to DB (mirror the PR-2
  task-state migration); small table keyed `(model, date)`.~~ **DONE
  2026-09-01** — schema v18 `gemini_model_state(model, day, exhausted, count)`;
  `core/llm/gemini.py` reads/writes it (helpers swallow DB errors → old
  "assume available" fallback so CLI/tests never break). Kills Mehran's
  cause (b): the fallback chain now stays on the SAME model across Fly
  restarts instead of re-probing and diverging. Test:
  `tests/test_gemini_model_state.py` (round-trip + durability).
- ~~Scoring `temperature → 0` for determinism (REQ-015/016).~~ **DONE
  2026-08-31** — per-call override on `generate_json` (scoring passes 0.0,
  generation keeps 0.4). Kills cause (a).
- ~~Score cache keyed on **resume-text hash** (not `resume_id`).~~ **DONE
  2026-08-31** — schema v17: `job_scores` PK re-keyed on the resume text hash
  (`resumes.text_hash`), resolved from `resume_id` inside `db.py` so no call
  site changed. A regenerated-but-equivalent resume now reuses its scores.
- ~~Investigate the regen truncation separately (writer / ai_regenerate).~~
  **FIXED 2026-09-01 — reproduced LIVE on Mehran's Fly app (`jobbotv2-hermana`,
  resume id 9 × job `li-4454079380`, aggressive level) and evidence-driven.**
  What it is NOT (ruled out by repro): a token cutoff. At the 8192 default the
  truncated run returned *complete, valid JSON with the full cover letter* —
  just 5 of 22 experience items. `generate_json` never raised MAX_TOKENS, so
  the model was **choosing** to emit ~5 items (interprets aggressive "collapse
  bullets" as "keep the top few"). ~20% of runs, non-deterministic (temp 0.4),
  same model each time (so not fallback divergence either). Two guessed fixes
  were tried and **both empirically refuted** on the machine, then reverted:
  (a) `max_output_tokens=16384` — irrelevant, it's not a token cutoff; (b) an
  `_OUTPUT_SCHEMA` "never drop an entry" rule — A/B on real data showed no
  effect (1/5 collapse with AND without it). **Actual fix:** a structural-
  fidelity guard in `core/llm/rewrite.py` (ADR-005 contract-layer pattern) —
  `_collapsed_sections` flags experience/education dropping below 60% of the
  original item count, `rewrite_resume` then retries once (per-call random →
  ~20%²≈4% residual) and restores any still-collapsed section verbatim from
  the original. No role/employer/degree can ever be silently lost. Live
  validation (6 guarded trials on Mehran's data): both catastrophic collapses
  (5/22) recovered to 22/22; legitimate aggressive trims (18–21/22) correctly
  pass through untouched. Test: `tests/test_rewrite_fidelity.py` (deterministic,
  fake client). **Note:** count-based threshold is a proxy — refining to true
  role-header counting was skipped (header detection is fragile; the 0.6 gap
  between collapse ~0.23 and legit trim ~0.82+ is clean).

Landed alongside the above (REQ-016 B-layer pass, 2026-08-31): the 5→3→1
`semantic_score.py` prompt reframe — coverage-anchored scoring + cross-language
rule + wrong-language gap (ADR-017/018), `PROMPT_VERSION` bumped.

REQ-016 A-layer (2026-08-31): `lite_score.rank()` wired at the score-batch
boundary then **ROLLED BACK** ([ADR-020](decisions/ADR-020-defer-lite-score-a-layer.md))
— the chain scores every job anyway, so it only reordered (no call saving) at
higher CPU and gave no cross-language gain. `affinity` retained; `lite_score`
unwired until a real top-N cap is chosen. A/B + determinism harnesses added
(`scripts/scoring_bakeoff.py --ab` / `--determinism`), now **batch-of-5** =
production path. **ACTION for Eduardo:** mark `data/ab_scoring_<date>.md` — the
ground-truth go/no-go on the NEW prompt. Batch findings: composition shifts
scores (Mehran 88 solo→75 in-batch), NEW less drifty than OLD, cross-language
wins clear (Andrea EN 45→62, wrong-language gap firing).

Determinism finding (2026-08-31, [ADR-019](decisions/ADR-019-gemini-scoring-nondeterministic-stability-via-cache.md)):
`--determinism` demo proved **temp=0 does NOT make Gemini deterministic** —
same model, same prompt, drift ±3–10 + band-edge bucket flips. Not fallback
divergence (model verified constant). Decision: user-facing stability = the
text-hash cache freezing the first score (not temperature); keep temp=0; ship an
honest tailor-tab disclaimer (`tailor.score_disclaimer`, EN/ES). Escalation if a
real user complains = median-of-3 on first write (deferred). ~~**Still open:**
persist gemini exhaustion/counts to DB (fallback divergence across restarts —
separate from this same-model finding); regen truncation bug.~~ **Both closed
2026-09-01 — see the two DONE/ADDRESSED bullets above.**

## What's the sprint
Section-based scoring (LLM produces per-section evidence, backend
does the math) + domain-neutral persona derived from resume context
(remove baked-in AEC assumptions in search seeds, matching, and
prompts). Requirements and ADRs already written; implementation is
what's left.

## 2026-08-26 kickoff — implementation decisions

Reading the code before touching it surfaced a gap: ADR-007 assumes
`role_label`/domain/seniority are already available resume signals;
in practice only `role_label` exists, and it's generated lazily by
`ui_web/routes/profile.py` on Profile visits — not guaranteed present
at scoring time, and not reachable from `core/` without an inverted
dependency. Raised as a 3-way architecture question; decided:

1. **Persona pipeline** — captured as [ADR-013](decisions/ADR-013-persona-source-shared-resume-profile.md).
   Shared resume-profile generation moves to `core/resume/ai_summary.py`,
   extended to also produce `domain` + `seniority`, callable from
   `score_jobs` with a generic fallback on failure.
2. **REQ-006 saved searches** — replace the 3 hardcoded AEC presets in
   `core/jobs/saved_searches.py` with domain-neutral content (keep the
   pre-baked/editable structure, just de-bias what's in it), and clean
   the AEC/"boyfriend" framing from comments.
3. **REQ-005 regression fixtures** — no real resume text or fixtures
   directory exists in this repo/environment (`data/` is gitignored).
   Building realistic *synthetic* fixtures for the AEC / non-AEC /
   career-switcher cases instead of real user resumes — committing
   real resume text to git is a separate data-governance call from the
   ephemeral per-request send to Gemini that GOV-001 covers. Fixtures
   are clearly labeled synthetic; swappable for real text later if
   provided.

## 2026-08-26 close-out — deferred / skipped items

- **Real resume fixtures.** Synthetic fixtures ship now (see decision 3
  above); swap in real (anonymized) resume text if/when provided —
  doesn't block the PR.
- **Full module split for the grounding guard-rail.** `/simplify`'s
  altitude review wanted `_grounding_ok`/`_term_grounded`/
  `_score_batch_grounded` pulled out of `semantic_score.py` into their
  own module. The actual duplication problem it was pointing at (three
  near-identical normalize/stem implementations) is fixed by extracting
  `core/matching/lexical.py`; a further file-size-only split was skipped
  as risking a `core/matching` import cycle for a stylistic win.
- **ADR-013's length.** `/code-review` flagged it (and the pre-existing
  ADR-012) as over CLAUDE.md's "under 150 words" ADR guideline. Left as
  written — every ADR since ADR-004 already runs well past that budget,
  and the Alternatives/Consequences sections are the parts the
  solution-architecture skill calls load-bearing.
- **Automated regression test for the `ai_summary` stale-cache fix.**
  `core/resume/ai_summary.py` doesn't accept a DB path override, so
  `get_or_generate` can't be exercised against an isolated test DB the
  way the rest of the suite tests `core/db.py` functions directly — the
  fix is covered by code inspection + the existing grounding test suite,
  not a dedicated test. Worth a path-injection param if this file grows
  more test surface.
- **`ui_web/templates/partials/job_card.html` keyboard-handling bug and
  ADR-012's word count**, both flagged by `/code-review` — both belong
  to REQ-012 (Sprint 8's fixed-viewport workspace), already merged to
  `main` before this branch forked. Out of this sprint's scope; not
  touched.

## 2026-08-25 hotfix detour (not Sprint 7)
Mehran feedback shipped as 6 commits in an unplanned session:
1. `08e9619` — cache key gains `lang` (schema v13 + migration).
2. `216c0c1` — feedback modal Send button (iOS Safari race).
3. `d4750aa` — translate Matched / Gaps / Gaps flagged headers.
4. `3f672f7` — north-star docs: `llm-surface.md` + `ADR-008`.
5. `a2c0423` — /simplify pass (3 cleanups).
6. `71fce5a` — reset feedback textarea on close (from /code-review).

Sprint hygiene done: /simplify pass ran, /code-review medium partial
(6/8 finders cut by session rate-limit — inline review closed the
gap; only surviving actionable finding was the textarea reset).

Known drift documented but NOT fixed in this detour (real work, own
session): `resume_suggestions` and `resume_ai_summary` caches carry
the same missing-`lang` bug class we fixed for `job_scores`.
Flagged in [llm-surface.md](architecture/llm-surface.md) under
"Known drift risks."

## 2026-08-25 PM — Mehran feedback dump (post-hotfix) — SHIPPED

**Status: shipped 2026-08-25.** Deployed to all 4 Fly apps (Melissa
`jobbotv2`, Mehran `-hermana`, Andrea `-andrea`, Sara `-melissa`).
Andrea validated end-to-end in her live session; Melissa hit + we
fixed one regression during rollout (see hotfixes below); Mehran /
Sara validation still pending on their own time.

**Sprint hygiene:** user explicitly skipped `/simplify` +
`/code-review` for this detour to move to a separate concern. If
we come back to it, run `/code-review low` (or `ultra`) — memory
`feedback_sprint_hygiene` says never `medium`.

**Andrea's open validation task:** confirm whether the 54→98 score
jump reproduces from "regenerate cleanly" alone (would be an
invalidation bug not covered by REQ-009) vs. from re-uploading the
PDF (expected — new `resume_id` = cache miss).

**Shipped scope:**
- REQ-007 destructive-action modals (`a0a7659`).
- REQ-008 jobs_results filter reactivity + card meta lookup (`a0a7659`).
- REQ-009 cache-key lang parity + schema v14 migration (`a0a7659`).
- REQ-010 + ADR-009 language-onboarding architectural doc (`a0a7659`).
- Bucket D — jobs UX polish (hide fr toggle on ES, hide dismissed on
  empty dataset, broaden `onlyNew` semantic, i18n load stages,
  personalised role placeholder, city placeholder incl. country) (`a0a7659`).
- Bucket F — full tailor-flow i18n sweep, 44 EN/ES keys (`a0a7659`).

**In-session hotfixes (rollout regressions):**
- `990132f` — tojson in x-data attribute broke jobs.html and
  tailor_panel.html (Melissa's browser leaked raw x-data as text).
  Fixed via `<script>` window globals; memory
  `feedback_tojson_in_html_attribute` updated with both patterns.
- `4b4e1ec` — `hideFrench: true` store default was invisibly active
  on UI=es after Bucket D hid the toggle. Coupled the value to UI
  language in `init()`.
- `3dcbc0b` → `3ebf9c4` → `7696df1` → `6b5dece` — four iterations
  on the split-viewport detail pane. Started with `sticky top-20 +
  self-start`, tried `items-start`-belt, cut to `position: fixed`
  (visually ugly overlap), landed on user proposal: aside is
  `position: absolute` inside a `relative` grid, JS sets `top` from
  clicked card's Y — card and pane share document flow, scroll
  together. Ships as `6b5dece`.

**Deferred / left as follow-up work:**
- Andrea's validation of the score-jump mechanic.
- Mehran / Sara feedback on all shipped fixes.
- `/simplify` + `/code-review low|ultra` sweep of the detour.
- REQ-010 implementation (docs only in this detour; the actual
  language-onboarding banner extension is its own sprint).

---

### Original PM dump (kept for retro)

**Filed as REQs (this session):**
- [REQ-007](requirements/REQ-007-restore-destructive-action-modals.md)
  — bucket C. Destructive-action buttons on Profile lost their
  confirm modal (likely regression from `79d3e6a` tiered
  data-destruction PR). ~30 min. **Highest severity — data loss
  risk.**
- [REQ-008](requirements/REQ-008-jobs-results-filter-reactivity.md)
  — bucket E. `min_score` and "solo nuevas" filters don't react to
  scores arriving via HTMX OOB swap during the batch chain. User
  sees 3 of 31 when it should be 21. ~1–2 h. **Product-breaking.**
- [REQ-009](requirements/REQ-009-cache-key-lang-parity.md) — bucket
  A. Apply the `job_scores` cache-key fix pattern to
  `resume_suggestions` (#7) and `resume_ai_summary` (#8). ~1–1.5 h.
  Closes the drift entry in llm-surface.md.

**Buckets D, F, B shipped in the same session (docs + code):**
- **Bucket D (code)** — jobs_results: hide FR toggle when UI=es;
  hide Dismissed toggle when dataset has zero dismissed;
  base.html filter store: `onlyNew` unions `is_new || new_since_expand`;
  city placeholder now includes country example; jobs.html:
  loading stages (search / multi / URL) go through `_()` + `tojson`
  so overlay speaks the user's language; job-title first placeholder
  personalises using `resume_ai_summary.role_label` when cached,
  falls back to generic; `filters.only_new.tooltip` reworded to
  match new semantic.
- **Bucket F (code)** — full tailor-flow i18n sweep. 44 new keys
  (EN + ES parity). Covers: drawer chrome (base.html), tailor_panel
  (setup, runs, level tiles, generate/generating buttons, TAILOR_STAGES),
  tailor_runs_list (in-progress row), tailor_result (fallback banner,
  ribbon, meta line, insight, resume/cover sections, action row).
  Level labels + descs now flow as i18n keys from the route
  (`jobs_tailor_open`), not hardcoded English strings.
- **Bucket B (docs)** — [REQ-010](requirements/REQ-010-explicit-language-onboarding.md)
  + [ADR-009](decisions/ADR-009-explicit-language-onboarding.md).
  Extend the geo first-visit banner to also ask UI + output
  language; retire silent `Accept-Language` overwrites. Implementation
  is a follow-up sprint — this pass captures the architectural
  decision only.

**Open question for the user:** confirm with Mehran which button
exactly triggered the 54→98 score jump. Code mechanics say re-upload
of PDF (new `resume_id` → cache miss); if she insists it was only
"regenerate cleanly", there's an invalidation bug not covered by
REQ-009.

**Session hygiene note:** `/code-review medium` earlier today burnt
6/8 finders on rate-limit. Next end-of-sprint pass use `low` or
`ultra`, not `medium`. Cap sub-agent parallelism at 3–4 Sonnet by
default.
