"""P3 Story mapping (ADR-048, REQ-041) — matches the candidate's account-level
Story Bank (P5/P6) to THIS interview's competencies (P1). For each competency it
picks the best story, says in one sentence why it fits, and how to angle it for
this company and role. No story fits → story_id null (the Stories tab renders a
"No story yet" gap; D4/Flow B5).

Unlike P1/P2, the mapping depends on an input that changes independently of the
prompt: the Story Bank. So the cache key folds a **content fingerprint of the
stories** into the version — edit or add a story and the mapping is a miss
(regenerate), never stale. Cache in `prep_artifacts` keyed
(interview, 'mapping', lang, version+fingerprint); temperature=0.0. A story_id
the bank didn't define, or a competency_id the brief didn't define, is dropped
(no dangling join, ADR-048).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

PROMPT_VERSION = "2026-09-21-mapping-v1"
ARTIFACT_KIND = "mapping"


@dataclass
class Mapping:
    competency_id: str
    story_id: Optional[str]
    why_it_fits: Optional[str]
    angle_for_this_role: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _stories_fingerprint(stories: list[dict]) -> str:
    """A short digest of the story set's CONTENT (not just ids) so any edit is a
    cache miss. Deterministic: sort by id, hash the STAR-bearing fields."""
    rows = sorted(
        (
            {k: str(s.get(k, "")) for k in
             ("id", "title", "situation", "task", "action", "result", "metric")}
            for s in stories if isinstance(s, dict)
        ),
        key=lambda r: r["id"],
    )
    blob = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _cache_version(stories: list[dict]) -> str:
    return f"{PROMPT_VERSION}:{_stories_fingerprint(stories)}"


def read_cached_mapping(
    interview_id: int, stories: list[dict], *, lang: Optional[str] = None, path=db.DB_PATH,
) -> Optional[list[Mapping]]:
    """Cache-only read for the CURRENT story set — no client, no generation.
    Readiness (D9) uses this to count mapped competencies without triggering P3.
    Returns None on a miss (mapping not built for this story fingerprint yet)."""
    if not interview_id:
        return None
    lang = _resolve_lang(lang)
    version = _cache_version(stories)
    cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
    return _row_to_mapping(cached) if cached is not None else None


def _row_to_mapping(row: dict) -> list[Mapping]:
    a = row.get("artifact") or {}
    items = a.get("mapping") if isinstance(a, dict) else None
    return _parse_mapping(items, valid_competencies=None, valid_stories=None)


def get_or_generate_mapping(
    interview: dict,
    competencies: list[dict],
    stories: list[dict],
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[list[Mapping]]:
    """Cache-aware entry point. `competencies` is P1's list; `stories` is the
    account Story Bank (may be empty → an all-null mapping, one gap per
    competency). Returns the mapping, generating + caching on a miss. None only
    when there are no competencies (nothing to map)."""
    interview_id = interview.get("id")
    if not interview_id or not competencies:
        return None
    lang = _resolve_lang(lang)
    version = _cache_version(stories)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
        if cached is not None:
            return _row_to_mapping(cached)

    valid_competencies = {str(c.get("id", "")).strip() for c in competencies if isinstance(c, dict)}
    valid_stories = {str(s.get("id", "")).strip() for s in stories if isinstance(s, dict)}

    # Empty bank: no LLM call — every competency is a known gap. Still cached so
    # the Stories tab renders instantly and consistently.
    if not stories:
        mapping = [Mapping(cid, None, None, None) for cid in sorted(valid_competencies)]
    else:
        if client.all_models_exhausted():
            return None
        mapping = _generate(interview, competencies, stories, client, lang=lang,
                            valid_competencies=valid_competencies, valid_stories=valid_stories)
        if mapping is None:
            return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(
        interview_id, ARTIFACT_KIND, lang, version,
        {"mapping": [m.to_dict() for m in mapping]}, model_used, path=path)
    return mapping


def _generate(
    interview: dict, competencies: list[dict], stories: list[dict], client: GeminiClient,
    *, lang: str, valid_competencies: set[str], valid_stories: set[str],
) -> Optional[list[Mapping]]:
    prompt = _build_prompt(interview, competencies, stories, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    items = raw.get("mapping") if isinstance(raw, dict) else None
    return _parse_mapping(items, valid_competencies=valid_competencies, valid_stories=valid_stories)


def _build_prompt(interview: dict, competencies: list[dict], stories: list[dict], *, lang: str) -> str:
    company = (interview.get("company") or "").strip() or "(unknown company)"
    role = (interview.get("role_title") or "").strip() or "(unknown role)"
    jd = P.clip(interview.get("jd_text") or "", P.MAX_JD_CHARS)
    jd_block = jd if jd else "(not provided — use the role title and competencies)"

    return f"""You are helping a candidate prepare for a {role} interview at {company}.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Match the candidate's saved stories to this interview's competencies.

Do this:
1. For each competency, pick the best story from the Story Bank. A story can be used for more than one competency, but prefer variety.
2. Say in one sentence why the story fits.
3. Say in one sentence how to angle the story for this company and role.
4. If no story fits a competency, set story_id to null (and why_it_fits / angle_for_this_role null).

Competencies (use these ids):
{P.format_competencies(competencies)}

Story Bank (use these story ids):
{P.format_stories(stories)}

Job description:
---
{jd_block}
---

Return JSON with this exact schema — no prose before or after:
{{
  "mapping": [
    {{ "competency_id": "c1", "story_id": "s3 | null",
       "why_it_fits": "string | null", "angle_for_this_role": "string | null" }}
  ]
}}"""


def _parse_mapping(
    items: Any, *, valid_competencies: Optional[set[str]], valid_stories: Optional[set[str]],
) -> list[Mapping]:
    """Keep one row per KNOWN competency. A competency_id the brief didn't define
    is dropped; a story_id the bank didn't define is nulled (and its why/angle
    with it — no explanation for a story we can't show). `valid_*=None` (the
    cache-read path) trusts stored ids as-is. De-dups repeated competency rows."""
    out: list[Mapping] = []
    if not isinstance(items, list):
        return out
    seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = str(it.get("competency_id", "")).strip()
        if not cid or cid in seen:
            continue
        if valid_competencies is not None and cid not in valid_competencies:
            continue
        sid = it.get("story_id")
        sid = str(sid).strip() if sid not in (None, "") else None
        if sid is not None and valid_stories is not None and sid not in valid_stories:
            sid = None
        if sid is None:
            why = angle = None
        else:
            why = str(it.get("why_it_fits") or "").strip() or None
            angle = str(it.get("angle_for_this_role") or "").strip() or None
        out.append(Mapping(competency_id=cid, story_id=sid, why_it_fits=why, angle_for_this_role=angle))
        seen.add(cid)
    return out
