"""Gemini-powered semantic scoring of jobs against a resume.

Section-based scoring (ADR-006): the LLM never returns a final score. It
returns per-section evidence — five fixed-weight sections owned here in
code — plus a separate list of hard requirements (met/partial/missing/
unknown, never folded into the average). The backend computes
`final_score = Σ(section_score × weight)` and maps it to the existing
verdict bands. This replaces the old "ask the LLM for one 0-100 number"
approach, which was non-deterministic run-to-run: giving the model a
fixed rubric to reason against, instead of a number to pick, is what
buys stability.

Domain-neutral persona (ADR-007 + ADR-013): the prompt opens with a
persona line built from the candidate's own resume (role/domain/
seniority, via `core.resume.ai_summary`), not a hardcoded industry
recruiter voice. The job side is always LLM-inferred independently —
no assumption that candidate and job share an industry.

Every result has: score (0-100, backend-computed), verdict (enum),
one-sentence overall reasoning, top matched/gaps (aggregated from
sections), the 5 section breakdowns, and hard requirements. Cached in
SQLite per (resume_id, job_id, lang), gated on (prompt_version,
scoring_version) — REQ-004's version lever (ADR-006).

Cost/latency:
- Batched 5 jobs per call (~2-4s vs ~15s doing them one by one) — ADR-010
  fixes this at 5 as the single source of truth (route imports
  DEFAULT_BATCH_SIZE from here so there's one number to change).
- Free tier: 1500 req/day → ~7500 unique jobs/day at batch=5
- Cache hits are free (SQLite lookup)

Reliability:
- Structured JSON output enforced by Gemini's json mode
- Prompt requires the model to echo the job_id it was given per item
- If a batch call fails, we retry the same jobs individually so one
  bad JD doesn't lose a whole page
- If the model omits a job from the response, that job is retried alone
- REQ-005 grounding guard-rail: every section's matched/gaps and every
  hard-requirement's evidence must check out against the resume before
  a result is trusted. A failing job gets one silent re-score; if it's
  still ungrounded, it's logged as bias-suspect and dropped rather than
  cached wrong (ADR-005 pattern — silence beats a lie).
- Persistence happens per-batch so partial progress survives crashes
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core import db, events
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.matching.lexical import normalize as _norm_text, stems as _term_stems
from core.resume import ai_summary
from core.settings import get_reasoning_language


def _resolve_lang(lang: str | None) -> str:
    """Fall back to the request's UI language when the caller hasn't
    pinned one. Keeps cache reads/writes and the prompt in agreement."""
    return lang if lang is not None else get_reasoning_language()


DEFAULT_BATCH_SIZE = 5
MAX_JD_CHARS = 2500       # truncate very long JDs — key reqs are near the top
# v0.5: bumped from 4000 → 12000 so certifications / additional-info / older
# roles at the tail of long resumes are still in the window Gemini reads.
# The pain this fixes: false-positive gaps like "driver license missing" when
# the resume DID list it in a section that lived past the 4000-char cutoff.
# Gemini's context is 1M+ tokens — 12k chars is a rounding error.
MAX_RESUME_CHARS = 12000

VERDICTS = ("strong_fit", "workable", "stretch", "poor_fit")

# ADR-006: five fixed-weight sections, owned in code — the LLM only ever
# returns evidence per section, never the final number. Dict order also
# sets the priority order for aggregating top-level matched/gaps (task
# below) — heaviest-weighted sections contribute first.
SECTION_WEIGHTS: dict[str, float] = {
    "experience": 0.30,
    "skills": 0.25,
    "role": 0.20,
    "domain": 0.15,
    "education": 0.10,
}
SECTION_KEYS = tuple(SECTION_WEIGHTS)
SECTION_LABELS: dict[str, str] = {
    "experience": "Experience & Achievements",
    "skills": "Skills & Tools",
    "role": "Role & Responsibility Alignment",
    "domain": "Industry / Domain Alignment",
    "education": "Education & Certifications",
}

HARD_REQ_STATUSES = ("met", "partial", "missing", "unknown")

# Bumped independently (ADR-006): PROMPT_VERSION when the instructions
# change, SCORING_VERSION when the weights/formula change. Either bump
# logically invalidates every cached job_scores row (version mismatch on
# read → recompute) without deleting history.
PROMPT_VERSION = "2026-08-26-section-rubric-domain-neutral"
SCORING_VERSION = "v1-five-section-weighted"


@dataclass
class SectionScore:
    score: int
    matched: list[str]
    gaps: list[str]
    reasoning: str


@dataclass
class HardRequirement:
    name: str
    status: str
    evidence: str


@dataclass
class ScoreResult:
    job_id: str
    score: int                              # backend-computed weighted final
    verdict: str                            # backend-computed from bands
    reasoning: str                          # LLM one-sentence overall reasoning
    matched: list[str]                      # aggregated top matches (<=5), for the card
    gaps: list[str]                         # aggregated top gaps (<=5), for the card
    model: str
    sections: dict[str, SectionScore] = field(default_factory=dict)
    hard_requirements: list[HardRequirement] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_jobs(
    resume_id: int,
    resume_text: str,
    jobs: list[dict],
    client: GeminiClient,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    use_cache: bool = True,
    lang: str | None = None,
) -> dict[str, ScoreResult]:
    """Score every job in `jobs` against the given resume.

    Returns a dict keyed by job_id. Cached jobs are looked up first (free);
    the rest are scored in batches. Individual job failures are silently
    skipped — the caller can detect them via missing keys.

    The `resume_text` should already be trimmed by the caller if desired;
    we truncate to MAX_RESUME_CHARS regardless for prompt sanity.

    `lang` is the language for reasoning/matched/gaps. Defaults to the
    current UI language via `get_reasoning_language()` — plumbed through
    both the cache key and the prompt so a language flip produces cache
    misses (regen in new language) instead of stale-language chips.
    """
    if not jobs or not resume_text.strip():
        return {}

    lang = _resolve_lang(lang)

    all_ids = [j["id"] for j in jobs]
    results: dict[str, ScoreResult] = {}

    if use_cache:
        cached = get_cached_scores(resume_id, all_ids, lang)
        for jid, row in cached.items():
            results[jid] = _row_to_result(row)

    uncached = [j for j in jobs if j["id"] not in results]
    if not uncached:
        return results

    # Short-circuit: if the whole model chain hit quota today, don't burn
    # ~2s per model probing. The results we do have (from cache) still ship.
    if client.all_models_exhausted():
        return results

    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    persona = ai_summary.persona_line(resume_id)
    resume_norm, resume_stems = _resume_ground_index(resume_snippet)

    for batch in _chunks(uncached, batch_size):
        # Re-check between batches — the first batch may have exhausted
        # the last available model; no point trying more.
        if client.all_models_exhausted():
            break
        try:
            batch_results = _score_batch_grounded(
                resume_snippet, batch, client, lang=lang, persona=persona,
                resume_id=resume_id, resume_norm=resume_norm, resume_stems=resume_stems,
            )
        except QuotaExhaustedError:
            # Fallback chain exhausted mid-run — stop cleanly with partial data.
            break
        for r in batch_results:
            results[r.job_id] = r
        if batch_results:
            save_scores(resume_id, [r.to_dict() for r in batch_results], lang)

    return results


def score_single_no_cache(
    resume_text: str,
    job: dict,
    client: GeminiClient,
    *,
    lang: str | None = None,
    resume_id: int | None = None,
    persona: str | None = None,
) -> ScoreResult | None:
    """One-shot score for arbitrary resume text vs a single job. Does NOT
    touch the DB cache — used to re-score a *tailored* resume where we don't
    want to pollute `job_scores` (which is keyed on the original resume_id).

    `resume_id`, when the caller has one, resolves the persona line (role/
    domain/seniority) — even a tailored resume's persona comes from the
    original resume's profile, since tailoring doesn't change who the
    candidate is. Pass `persona` directly instead when the caller already
    resolved it (e.g. the tailor route also calls `rewrite_resume` for the
    same resume_id in the same request — resolve once, pass to both,
    rather than triggering `ai_summary.persona_line` twice).

    Returns None if the model refuses / quota is out / response is malformed.
    """
    if not resume_text.strip() or not job:
        return None
    if client.all_models_exhausted():
        return None
    lang = _resolve_lang(lang)
    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    if persona is None:
        persona = ai_summary.persona_line(resume_id)
    resume_norm, resume_stems = _resume_ground_index(resume_snippet)
    try:
        results = _score_batch_grounded(
            resume_snippet, [job], client, lang=lang, persona=persona, resume_id=resume_id,
            resume_norm=resume_norm, resume_stems=resume_stems,
        )
    except QuotaExhaustedError:
        return None
    return results[0] if results else None


def score_stats(
    results: dict[str, ScoreResult],
    all_job_ids: list[str],
    resume_id: int,
    lang: str | None = None,
) -> dict[str, int]:
    """Small helper for the UI: how many scores came from cache vs fresh in
    this render. Doesn't hit Gemini — pure SQLite lookup."""
    lang = _resolve_lang(lang)
    cached = get_cached_scores(resume_id, all_job_ids, lang)
    total = len(all_job_ids)
    from_cache = sum(1 for jid in all_job_ids if jid in cached)
    fresh = sum(1 for jid in all_job_ids if jid in results and jid not in cached)
    return {"total": total, "from_cache": from_cache, "fresh": fresh}


def get_cached_scores(resume_id: int, job_ids: list[str], lang: str) -> dict[str, dict]:
    """`db.get_cached_scores` with `PROMPT_VERSION`/`SCORING_VERSION` baked
    in. Callers outside this module (routes) shouldn't need to know
    scoring is versioned or import the constants themselves — this is the
    one place that spells them out."""
    return db.get_cached_scores(resume_id, job_ids, lang, PROMPT_VERSION, SCORING_VERSION)


def save_scores(resume_id: int, scores: list[dict], lang: str) -> int:
    """`db.save_scores` with `PROMPT_VERSION`/`SCORING_VERSION` baked in."""
    return db.save_scores(resume_id, scores, lang, PROMPT_VERSION, SCORING_VERSION)


# ---------- backend math (ADR-006) ----------

def _final_score(sections: dict[str, SectionScore]) -> int:
    total = sum(sections[k].score * SECTION_WEIGHTS[k] for k in SECTION_KEYS)
    return max(0, min(100, round(total)))


def _verdict_from_score(score: int) -> str:
    if score >= 85:
        return "strong_fit"
    if score >= 65:
        return "workable"
    if score >= 40:
        return "stretch"
    return "poor_fit"


def _aggregate_top(sections: dict[str, SectionScore], attr: str, max_items: int = 5) -> list[str]:
    """Merge one field (matched/gaps) across sections into a single
    card-facing list, deduped, heaviest-weighted section first. Backend-
    computed (not asked of the LLM a second time) so the card's summary
    is guaranteed to be a subset of what the grounding check already
    verified at the section level."""
    seen: set[str] = set()
    out: list[str] = []
    for key in SECTION_KEYS:
        for term in getattr(sections[key], attr):
            norm = term.strip().lower()
            if norm and norm not in seen:
                seen.add(norm)
                out.append(term.strip())
                if len(out) >= max_items:
                    return out
    return out


# ---------- REQ-005 grounding guard-rail ----------
# Normalize/stem via `core.matching.lexical` (dependency-free — no
# scikit-learn/numpy on this hot path). `core.matching.tfidf_match` uses
# the same shared functions instead of its own copy.

def _resume_ground_index(resume: str) -> tuple[str, set[str]]:
    """One tokenize-and-stem pass over the resume text, reused across a
    whole `score_jobs` call (and all its batches/retries) instead of
    recomputing per batch."""
    norm = _norm_text(resume)
    stems: set[str] = set()
    for w in norm.split():
        stems.update(_term_stems(w))
    return norm, stems


def _term_grounded(term: str, resume_norm: str, resume_stems: set[str]) -> bool:
    """Tolerant check: does `term` check out against the resume? Exact
    substring match, or (for multi-word terms) every significant word's
    stem is present. Deliberately lenient — this is a backstop against
    flagrant hallucination, not a semantic-equivalence judge (the prompt
    itself carries the "check synonyms before flagging a gap" rubric)."""
    t = _norm_text(term)
    if not t:
        return True
    if t in resume_norm:
        return True
    words = [w for w in t.split() if len(w) > 2]
    if not words:
        return False
    return all(_term_stems(w) & resume_stems for w in words)


def _grounding_ok(result: ScoreResult, resume_norm: str, resume_stems: set[str]) -> bool:
    """REQ-005 runtime guard-rail: every section's `matched` must check
    out against the resume (a claimed match that isn't there is reward
    inflation); every section's `gaps` must NOT check out (a "gap" that's
    actually present is a hallucinated, possibly bias-driven, false
    negative); every hard-requirement's evidence must check out when the
    requirement is claimed met/partial."""
    for section in result.sections.values():
        for term in section.matched:
            if not _term_grounded(term, resume_norm, resume_stems):
                return False
        for term in section.gaps:
            if _term_grounded(term, resume_norm, resume_stems):
                return False
    for hr in result.hard_requirements:
        if hr.status in ("met", "partial"):
            if not hr.evidence.strip() or not _term_grounded(hr.evidence, resume_norm, resume_stems):
                return False
    return True


def _score_batch_grounded(
    resume: str,
    jobs: list[dict],
    client: GeminiClient,
    *,
    lang: str,
    persona: str,
    resume_id: int | None,
    resume_norm: str,
    resume_stems: set[str],
) -> list[ScoreResult]:
    """Score `jobs`, then apply the grounding guard-rail on top. Any result
    that fails grounding gets ONE re-score (fresh LLM call on just that
    job); if it's still ungrounded, log it bias-suspect and drop it —
    never cache a result we can't stand behind (ADR-005 pattern: silence
    beats a lie).

    `resume_norm`/`resume_stems` come from `_resume_ground_index(resume)`
    — computed ONCE by the caller (per `score_jobs`/`score_single_no_cache`
    call, not per batch) since they're identical across every batch and
    retry for the same resume."""
    results = _score_batch(resume, jobs, client, lang=lang, persona=persona)
    if not results:
        return results

    grounded = [r for r in results if _grounding_ok(r, resume_norm, resume_stems)]
    if len(grounded) == len(results):
        return grounded

    ungrounded_ids = {r.job_id for r in results} - {r.job_id for r in grounded}
    retry_jobs = [j for j in jobs if j["id"] in ungrounded_ids]
    if not retry_jobs:
        return grounded

    try:
        retried = _score_batch(resume, retry_jobs, client, lang=lang, persona=persona)
    except QuotaExhaustedError:
        # Quota ran out mid-retry — keep the already-grounded results from
        # this batch rather than losing them; the caller's next-batch
        # `client.all_models_exhausted()` check stops further batches.
        return grounded
    for r in retried:
        if _grounding_ok(r, resume_norm, resume_stems):
            grounded.append(r)
        else:
            events.track(
                events.SCORING_BIAS_SUSPECT,
                job_id=r.job_id,
                resume_id=resume_id,
                model=r.model,
            )
    return grounded


# ---------- batching + prompt ----------

def _score_batch(
    resume: str,
    jobs: list[dict],
    client: GeminiClient,
    *,
    lang: str,
    persona: str,
) -> list[ScoreResult]:
    """Score one batch. On non-quota failure, retry each job individually
    (unless already at size 1, which gives up silently). On QuotaExhausted,
    propagate up so callers can stop early. On partial response (missing
    job_ids), retry the missing ones individually.

    `lang` is passed by the top-level entry point (score_jobs /
    score_single_no_cache) — user-facing strings (reasoning, matched,
    gaps) render in the UI, so they must follow the current UI language
    (Spanish UI + English gaps reads as broken). The cache key includes
    lang too so a flip doesn't return stale-language rows.

    `persona` is the domain-neutral candidate descriptor from
    `core.resume.ai_summary.persona_line` (ADR-007 + ADR-013) — fixed
    for the whole call so every job in a batch judges against the same
    frame."""
    prompt = _build_prompt(resume, jobs, persona=persona, reasoning_language=lang)
    try:
        raw = client.generate_json(prompt)
    except QuotaExhaustedError:
        raise   # bubble up — no point retrying individually
    except GeminiError:
        if len(jobs) == 1:
            return []
        out: list[ScoreResult] = []
        for j in jobs:
            try:
                out.extend(_score_batch(resume, [j], client, lang=lang, persona=persona))
            except QuotaExhaustedError:
                raise
        return out

    # last_model_used is set by generate_json to whichever model in the
    # chain actually served this request. Fall back to model_name if
    # somehow unset (shouldn't happen post-success).
    model_used = client.last_model_used or client.model_name or "unknown"
    parsed = _parse_response(raw, jobs, model_used)
    returned = {r.job_id for r in parsed}
    missing = [j for j in jobs if j["id"] not in returned]

    if missing and len(jobs) > 1:
        for j in missing:
            try:
                parsed.extend(_score_batch(resume, [j], client, lang=lang, persona=persona))
            except QuotaExhaustedError:
                # Return what we got so far — outer loop stops on the next call
                break

    return parsed


def _build_prompt(resume: str, jobs: list[dict], *, persona: str, reasoning_language: str = "en") -> str:
    """Craft a batch-scoring prompt that keeps each job's judgment isolated.

    Design notes:
    - Every job is wrapped in <JOB job_id="..."> — the model must echo that
      exact id in each output row. Any mismatch is dropped on parse.
    - Five fixed-weight sections (ADR-006) replace the old single 0-100
      ask — the model reasons against a rubric per section instead of
      picking one number, which is what makes re-scoring stable.
    - The persona line (ADR-007) is the ONLY place candidate identity
      enters the prompt — it's derived from the resume itself, never
      hardcoded to one industry, so the same prompt works for any domain.
    - The job's own industry/seniority/hard-vs-soft reqs are always
      LLM-inferred from the JD — never assumed to match the candidate's.
    - "Score each job INDEPENDENTLY" is repeated because Gemini's default
      is to compare items in a batch, which drags down mid-tier scores.
    """
    job_blocks = []
    for j in jobs:
        jd = (j.get("description") or "").strip()[:MAX_JD_CHARS]
        title = j.get("title") or "(unknown title)"
        company = j.get("company") or "(unknown company)"
        location = j.get("location") or ""
        job_blocks.append(
            f'<JOB job_id="{j["id"]}">\n'
            f'Title: {title}\n'
            f'Company: {company}\n'
            f'Location: {location}\n'
            f'Description:\n{jd}\n'
            f'</JOB>'
        )
    jobs_str = "\n\n".join(job_blocks)
    n = len(jobs)

    from core.settings import language_instruction

    section_rubric = "\n".join(
        f"  - {SECTION_LABELS[k]} (\"{k}\", weight {int(SECTION_WEIGHTS[k] * 100)}%)"
        for k in SECTION_KEYS
    )

    return f"""You are an expert recruiter evaluating job postings for {persona}, based on the resume below. For each job, read its own description to judge its role, responsibilities, required skills, industry, seniority, and hard vs soft requirements — the job may or may not be in the same industry as the candidate; assess transferable experience explicitly rather than assuming a match or a mismatch. Focus on real skill overlap, seniority alignment, and whether this specific candidate could realistically succeed in the role.

{language_instruction(reasoning_language)}

CANDIDATE RESUME:
---
{resume}
---

Below are {n} independent job postings. Score EACH one against the resume above, across FIVE fixed sections:
{section_rubric}

For EACH section, return {{"score": 0-100, "matched": [...], "gaps": [...], "reasoning": "one short phrase"}}.
SECTION SCORING RUBRIC (be strict — do not inflate; score each section independently of the others):
- 85-100: clear, direct alignment on this section's own criteria
- 65-84: meets most of this section's criteria; minor gaps tailoring could close
- 40-64: significant gaps in this section, but genuine transferable strength exists
- 0-39: little to no alignment on this section's criteria

Also return hard_requirements: any MANDATORY requirement the JD states explicitly (certification, work authorization, minimum years, specific degree, language fluency, on-site/security clearance, etc). For each: {{"name": "...", "status": "met|partial|missing|unknown", "evidence": "..."}}. "evidence" must be a short, real reference to what you saw (resume text for met/partial; the JD's own wording for missing/unknown). Empty list if the JD states no hard requirements. Hard requirements are separate from the five sections — do NOT fold them into any section's score.

CRITICAL RULES:
1. Score each job INDEPENDENTLY. Do NOT rank or compare jobs to each other. A batch of 6 could all score high, or all score low, on their own merits.
2. Base every judgment on THIS candidate's actual resume above, not generic advice.
3. "matched" (per section) = concrete skills, tools, or experience present in BOTH the resume and the JD. Max 5 per section. Prefer specific, concrete terms over generic soft skills.
4. "gaps" (per section) = requirements from the JD that are TRULY MISSING from the resume, within that section's scope. Max 5 per section.
   BEFORE listing ANY gap, verify the resume does NOT mention it in any form — including abbreviations, synonyms, or sections like "Additional Information", "Certifications", "Licenses", tail bullet points.
   Common false positives to AVOID:
     - "Driver license" when the resume says "Valid Class G license" or "Ontario driver's licence"
     - "AutoCAD" when the resume lists "Autodesk suite" or "AutoCAD 2024"
     - "Bilingual" when the resume has "Fluent in French and English"
     - "Bachelor's degree" when the resume shows "BASc, Civil Engineering, 2020"
   These are illustrative of the PATTERN (check synonyms/abbreviations before flagging), not specific to any one industry — apply the same scrutiny regardless of what field the candidate or job is in.
   If a JD requirement appears in ANY form in the resume — even abbreviated, in a footer section, or phrased differently — it is NOT a gap.
5. Reward transferable experience explicitly: a candidate from a different industry with directly applicable skills, scope, or seniority should not be penalized in Role or Skills sections just for an Industry/Domain mismatch — that mismatch belongs in the Industry/Domain section alone.
6. Distinguish a real skill gap from a missing keyword — if the resume demonstrates the underlying capability under different wording, it's a match, not a gap.
7. "reasoning" (per section) = a few words, direct, no fluff.
8. Use the EXACT job_id string from each <JOB> tag. Do not invent, shorten, or reformat.
9. Also return ONE overall "reasoning" sentence (max 22 words, direct, no fluff, citing concrete evidence) — a human-readable summary of the fit. Do not begin it with the verdict label or any variant (strong_fit, Strong fit, workable, stretch, poor_fit, etc.).

JOBS TO SCORE:

{jobs_str}

Return JSON with this exact schema — no prose before or after:
{{
  "scores": [
    {{
      "job_id": "<exact string from JOB tag>",
      "sections": {{
        "experience": {{"score": 0, "matched": [], "gaps": [], "reasoning": ""}},
        "skills":     {{"score": 0, "matched": [], "gaps": [], "reasoning": ""}},
        "role":       {{"score": 0, "matched": [], "gaps": [], "reasoning": ""}},
        "domain":     {{"score": 0, "matched": [], "gaps": [], "reasoning": ""}},
        "education":  {{"score": 0, "matched": [], "gaps": [], "reasoning": ""}}
      }},
      "hard_requirements": [{{"name": "...", "status": "met", "evidence": "..."}}],
      "reasoning": "<one sentence overall>"
    }}
  ]
}}

The scores array MUST contain exactly {n} entries — one per job_id above. Do not omit or duplicate any job. Every one of the five section keys must be present for every job.
"""


# ---------- response parsing ----------

def _parse_response(
    raw: dict,
    jobs: list[dict],
    model: str,
) -> list[ScoreResult]:
    """Extract valid ScoreResults from Gemini's JSON. Defensive against:
    - Missing/extra job_ids
    - Out-of-range section scores
    - Missing/malformed sections (defaulted to a 0-score placeholder)
    - Wrong types on matched/gaps/hard_requirements
    - Duplicate job_ids in the response (first one wins)
    """
    scores_raw = raw.get("scores")
    if not isinstance(scores_raw, list):
        return []

    expected = {j["id"] for j in jobs}
    seen: set[str] = set()
    out: list[ScoreResult] = []

    for item in scores_raw:
        if not isinstance(item, dict):
            continue
        jid = str(item.get("job_id", "")).strip()
        if not jid or jid not in expected or jid in seen:
            continue
        seen.add(jid)

        sections = _parse_sections(item.get("sections"))
        hard_requirements = _parse_hard_requirements(item.get("hard_requirements"))
        reasoning = str(item.get("reasoning", "")).strip()
        reasoning = re.sub(
            r"^(strong[_ ]fit|workable|stretch|poor[_ ]fit)[,:\s]+",
            "",
            reasoning,
            flags=re.IGNORECASE,
        ).strip()
        if reasoning:
            reasoning = reasoning[0].upper() + reasoning[1:]

        final_score = _final_score(sections)
        verdict = _verdict_from_score(final_score)
        matched = _aggregate_top(sections, "matched")
        gaps = _aggregate_top(sections, "gaps")

        out.append(ScoreResult(
            job_id=jid,
            score=final_score,
            verdict=verdict,
            reasoning=reasoning,
            matched=matched,
            gaps=gaps,
            model=model,
            sections=sections,
            hard_requirements=hard_requirements,
        ))

    return out


def _parse_sections(raw: Any) -> dict[str, SectionScore]:
    sections: dict[str, SectionScore] = {}
    raw = raw if isinstance(raw, dict) else {}
    for key in SECTION_KEYS:
        entry = raw.get(key)
        if not isinstance(entry, dict):
            sections[key] = SectionScore(score=0, matched=[], gaps=[], reasoning="")
            continue
        try:
            score = int(entry.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))
        sections[key] = SectionScore(
            score=score,
            matched=_coerce_str_list(entry.get("matched"), max_items=5),
            gaps=_coerce_str_list(entry.get("gaps"), max_items=5),
            reasoning=str(entry.get("reasoning", "")).strip(),
        )
    return sections


def _parse_hard_requirements(raw: Any) -> list[HardRequirement]:
    if not isinstance(raw, list):
        return []
    out: list[HardRequirement] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()[:120]
        if not name:
            continue
        status = str(item.get("status", "")).strip().lower()
        if status not in HARD_REQ_STATUSES:
            status = "unknown"
        evidence = str(item.get("evidence", "")).strip()
        if len(evidence) > 240:
            # Cut at a word boundary, not mid-word — a hard cutoff can chop
            # a real quote in half and make it fail the grounding check
            # below (_term_grounded splits on whitespace and stems each
            # word; a fragment like "p" from a severed "P.E." has no stem
            # match, so a truthful quote would wrongly fail grounding).
            evidence = evidence[:240].rsplit(" ", 1)[0]
        out.append(HardRequirement(name=name, status=status, evidence=evidence))
        if len(out) >= 10:
            break
    return out


def _coerce_str_list(value: Any, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
            if len(out) >= max_items:
                break
    return out


def _row_to_result(row: dict) -> ScoreResult:
    """DB row → ScoreResult. JSON blobs live as strings on disk — reuse
    the same `_parse_sections`/`_parse_hard_requirements` validation used
    for fresh LLM output, so a malformed cached row gets the same
    defensive clamping (score range, list caps, status whitelist) instead
    of a separate, weaker hand-rolled reconstruction."""
    sections = _parse_sections(_safe_json_dict(row.get("sections_json")))
    hard_requirements = _parse_hard_requirements(_safe_json_raw(row.get("hard_requirements_json")))
    return ScoreResult(
        job_id=row["job_id"],
        score=int(row["score"]),
        verdict=row["verdict"],
        reasoning=row["reasoning"] or "",
        matched=_safe_json_list(row.get("matched_json")),
        gaps=_safe_json_list(row.get("gaps_json")),
        model=row.get("model") or "",
        sections=sections,
        hard_requirements=hard_requirements,
    )


def _safe_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _safe_json_dict(value: Any) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_json_raw(value: Any) -> Any:
    """Like `_safe_json_dict`/`_safe_json_list` but returns whatever type
    decoded (or None on failure) — for callers like `_parse_hard_requirements`
    that already validate shape themselves and don't want elements coerced
    to strings."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
