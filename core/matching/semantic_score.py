"""Gemini-powered semantic scoring of jobs against a resume.

Replaces raw TF-IDF cosine similarity with an LLM that understands AEC
vocabulary, seniority, and can explain *why* a job is a good/bad fit.

Every result has: score (0-100), verdict (enum), one-sentence reasoning,
top matched skills, top gaps. Cached in SQLite per (resume_id, job_id).

Cost/latency:
- Batched 6 jobs per call (~2-4s vs ~15s doing them one by one)
- Free tier: 1500 req/day → ~9000 unique jobs/day at batch=6
- Cache hits are free (SQLite lookup)

Reliability:
- Structured JSON output enforced by Gemini's json mode
- Prompt requires the model to echo the job_id it was given per item
- If a batch call fails, we retry the same jobs individually so one
  bad JD doesn't lose a whole page
- If the model omits a job from the response, that job is retried alone
- Persistence happens per-batch so partial progress survives crashes
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError


DEFAULT_BATCH_SIZE = 6
MAX_JD_CHARS = 2500       # truncate very long JDs — key reqs are near the top
MAX_RESUME_CHARS = 4000   # 2-page resume ≈ 3-4k chars

VERDICTS = ("strong_fit", "workable", "stretch", "poor_fit")


@dataclass
class ScoreResult:
    job_id: str
    score: int
    verdict: str
    reasoning: str
    matched: list[str]
    gaps: list[str]
    model: str

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
) -> dict[str, ScoreResult]:
    """Score every job in `jobs` against the given resume.

    Returns a dict keyed by job_id. Cached jobs are looked up first (free);
    the rest are scored in batches. Individual job failures are silently
    skipped — the caller can detect them via missing keys.

    The `resume_text` should already be trimmed by the caller if desired;
    we truncate to MAX_RESUME_CHARS regardless for prompt sanity.
    """
    if not jobs or not resume_text.strip():
        return {}

    all_ids = [j["id"] for j in jobs]
    results: dict[str, ScoreResult] = {}

    if use_cache:
        for jid, row in db.get_cached_scores(resume_id, all_ids).items():
            results[jid] = _row_to_result(row)

    uncached = [j for j in jobs if j["id"] not in results]
    if not uncached:
        return results

    # Short-circuit: if the whole model chain hit quota today, don't burn
    # ~2s per model probing. The results we do have (from cache) still ship.
    if client.all_models_exhausted():
        return results

    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]

    for batch in _chunks(uncached, batch_size):
        # Re-check between batches — the first batch may have exhausted
        # the last available model; no point trying more.
        if client.all_models_exhausted():
            break
        try:
            batch_results = _score_batch(resume_snippet, batch, client)
        except QuotaExhaustedError:
            # Fallback chain exhausted mid-run — stop cleanly with partial data.
            break
        for r in batch_results:
            results[r.job_id] = r
        if batch_results:
            db.save_scores(resume_id, [r.to_dict() for r in batch_results])

    return results


def score_single_no_cache(
    resume_text: str,
    job: dict,
    client: GeminiClient,
) -> ScoreResult | None:
    """One-shot score for arbitrary resume text vs a single job. Does NOT
    touch the DB cache — used to re-score a *tailored* resume where we don't
    want to pollute `job_scores` (which is keyed on the original resume_id).

    Returns None if the model refuses / quota is out / response is malformed.
    """
    if not resume_text.strip() or not job:
        return None
    if client.all_models_exhausted():
        return None
    resume_snippet = resume_text.strip()[:MAX_RESUME_CHARS]
    try:
        results = _score_batch(resume_snippet, [job], client)
    except QuotaExhaustedError:
        return None
    return results[0] if results else None


def score_stats(
    results: dict[str, ScoreResult],
    all_job_ids: list[str],
    resume_id: int,
) -> dict[str, int]:
    """Small helper for the UI: how many scores came from cache vs fresh in
    this render. Doesn't hit Gemini — pure SQLite lookup."""
    cached = db.get_cached_scores(resume_id, all_job_ids)
    total = len(all_job_ids)
    from_cache = sum(1 for jid in all_job_ids if jid in cached)
    fresh = sum(1 for jid in all_job_ids if jid in results and jid not in cached)
    return {"total": total, "from_cache": from_cache, "fresh": fresh}


# ---------- batching + prompt ----------

def _score_batch(
    resume: str,
    jobs: list[dict],
    client: GeminiClient,
) -> list[ScoreResult]:
    """Score one batch. On non-quota failure, retry each job individually
    (unless already at size 1, which gives up silently). On QuotaExhausted,
    propagate up so callers can stop early. On partial response (missing
    job_ids), retry the missing ones individually."""
    prompt = _build_prompt(resume, jobs)
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
                out.extend(_score_batch(resume, [j], client))
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
                parsed.extend(_score_batch(resume, [j], client))
            except QuotaExhaustedError:
                # Return what we got so far — outer loop stops on the next call
                break

    return parsed


def _build_prompt(resume: str, jobs: list[dict]) -> str:
    """Craft a batch-scoring prompt that keeps each job's judgment isolated.

    Design notes:
    - Every job is wrapped in <JOB job_id="..."> — the model must echo that
      exact id in each output row. Any mismatch is dropped on parse.
    - The rubric is explicit and numeric so scores are comparable across
      runs (drift is Gemini's biggest weakness here).
    - "Score each job INDEPENDENTLY" is repeated because Gemini's default
      is to compare items in a batch, which drags down mid-tier scores.
    - Reasoning is capped at one sentence to prevent generic filler.
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

    return f"""You are an expert AEC (architecture / engineering / construction) recruiter evaluating job postings against ONE candidate's resume. Focus on real skill overlap, seniority alignment, and whether this specific candidate could realistically succeed in the role.

CANDIDATE RESUME:
---
{resume}
---

Below are {n} independent job postings. Score EACH one against the candidate above.

SCORING RUBRIC (be strict — do not inflate):
- 85-100 (strong_fit): clear alignment on core requirements AND seniority; candidate could apply with minimal tailoring
- 65-84  (workable): meets most core reqs; a few gaps that tailoring can address
- 40-64  (stretch): significant gaps but genuine transferable skills exist
- 0-39   (poor_fit): wrong domain, wrong seniority, or fundamentally different role

CRITICAL RULES:
1. Score each job INDEPENDENTLY. Do NOT rank or compare jobs to each other. A batch of 6 could all be strong_fit, or all poor_fit — score on absolute merit vs the candidate.
2. Base every judgment on THIS candidate's actual resume above, not generic advice.
3. "matched" = concrete skills, tools, or experience present in BOTH the resume and the JD. Max 5. Prefer specific tools (Revit, Navisworks) over generic soft skills.
4. "gaps" = requirements the JD asks for that are missing or weak in the resume. Max 5. Concrete tools/certs/domains only.
5. "reasoning" = ONE sentence, direct, no fluff. Start with the verdict word. Reference specific evidence from the resume or JD.
6. Use the EXACT job_id string from each <JOB> tag. Do not invent, shorten, or reformat.

JOBS TO SCORE:

{jobs_str}

Return JSON with this exact schema — no prose before or after:
{{
  "scores": [
    {{
      "job_id": "<exact string from JOB tag>",
      "score": <integer 0-100>,
      "verdict": "<strong_fit | workable | stretch | poor_fit>",
      "reasoning": "<one sentence>",
      "matched": ["skill1", "skill2"],
      "gaps": ["gap1", "gap2"]
    }}
  ]
}}

The scores array MUST contain exactly {n} entries — one per job_id above. Do not omit or duplicate any job.
"""


# ---------- response parsing ----------

def _parse_response(
    raw: dict,
    jobs: list[dict],
    model: str,
) -> list[ScoreResult]:
    """Extract valid ScoreResults from Gemini's JSON. Defensive against:
    - Missing/extra job_ids
    - Out-of-range scores
    - Missing/invalid verdicts (inferred from score)
    - Wrong types on matched/gaps
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

        try:
            score = int(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))

        verdict = str(item.get("verdict", "")).strip().lower()
        if verdict not in VERDICTS:
            verdict = _verdict_from_score(score)

        reasoning = str(item.get("reasoning", "")).strip()
        matched = _coerce_str_list(item.get("matched"), max_items=5)
        gaps = _coerce_str_list(item.get("gaps"), max_items=5)

        out.append(ScoreResult(
            job_id=jid,
            score=score,
            verdict=verdict,
            reasoning=reasoning,
            matched=matched,
            gaps=gaps,
            model=model,
        ))

    return out


def _verdict_from_score(score: int) -> str:
    if score >= 85:
        return "strong_fit"
    if score >= 65:
        return "workable"
    if score >= 40:
        return "stretch"
    return "poor_fit"


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
    """DB row → ScoreResult. Matched/gaps live as JSON strings on disk."""
    return ScoreResult(
        job_id=row["job_id"],
        score=int(row["score"]),
        verdict=row["verdict"],
        reasoning=row["reasoning"] or "",
        matched=_safe_json_list(row.get("matched_json")),
        gaps=_safe_json_list(row.get("gaps_json")),
        model=row.get("model") or "",
    )


def _safe_json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]
