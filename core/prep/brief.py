"""P1 Brief (ADR-048, REQ-041) — the first and load-bearing call in the Prep
pipeline. Reads the JD + company research + résumé and produces the interview
brief the whole toolkit hangs off:

  - role_summary, company_snapshot (each point cites its source URL — D3),
  - competencies[] (4–6, derived from the JD) with, per competency, what a
    strong answer shows AND a résumé-evidence band (strong/solid/needs_work),
  - gaps[] each with one concrete prep action,
  - interviewer_lens[] (from the interviewer's TITLE + round type — never a
    profile, D3), and friction_points[].

The competencies carry stable ids (c1, c2, …) — P2/P3/P4 join on them (ADR-048),
so this call runs FIRST and its result is cached before the toolkit fans out.
Read-only cache in `prep_artifacts` keyed (interview, lang, prompt_version);
temperature=0.0 for reproducibility. Grounded-or-honest: no research → the brief
still works from the JD, with an empty company_snapshot (never invented).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

PROMPT_VERSION = "2026-09-30-brief-v4"
ARTIFACT_KIND = "brief"

MIN_COMPETENCIES = 4
MAX_COMPETENCIES = 6
MAX_GAPS = 3
MAX_LENS = 3
MAX_FRICTION = 3
MAX_CLARIFY_QUESTIONS = 4


@dataclass
class CompanyPoint:
    point: str
    source_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"point": self.point, "source_url": self.source_url}


@dataclass
class Competency:
    id: str
    name: str
    what_good_looks_like: str
    resume_match: str = P.DEFAULT_BAND        # strong | solid | needs_work
    evidence: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Gap:
    competency_id: Optional[str]
    gap: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClarifyQuestion:
    """A question TO the candidate about the HOW behind something ALREADY on the
    résumé that this interview will lean on — the method, the tools, what they
    personally did, how the action produced the result (ADR-058). Never a request
    for new achievements: the company already has the résumé; we structure it.
    Asked as the first step of Get Ready; answers live in prep_artifacts 'facts'."""
    id: str
    question: str
    example: str = ""                    # first-person FORMAT sample (the placeholder)
    competency_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Brief:
    role_summary: str = ""
    company_snapshot: list[CompanyPoint] = field(default_factory=list)
    competencies: list[Competency] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    interviewer_lens: list[str] = field(default_factory=list)
    friction_points: list[str] = field(default_factory=list)
    clarify_questions: list[ClarifyQuestion] = field(default_factory=list)
    created_at: str = ""

    def is_empty(self) -> bool:
        # The competencies ARE the brief — without them the toolkit can't fan
        # out. A brief with only a role summary is useless downstream.
        return not self.competencies

    def to_dict_for_cache(self) -> dict[str, Any]:
        return {
            "role_summary": self.role_summary,
            "company_snapshot": [p.to_dict() for p in self.company_snapshot],
            "competencies": [c.to_dict() for c in self.competencies],
            "gaps": [g.to_dict() for g in self.gaps],
            "interviewer_lens": self.interviewer_lens,
            "friction_points": self.friction_points,
            "clarify_questions": [f.to_dict() for f in self.clarify_questions],
        }


def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _row_to_brief(row: dict) -> Brief:
    a = row.get("artifact") or {}
    b = _parse_brief(a)
    b.created_at = row.get("created_at", "")
    return b


def get_or_generate_brief(
    interview: dict,
    resume_text: str,
    client: GeminiClient,
    *,
    research: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[Brief]:
    """Cache-aware entry point. `interview` is an `interviews` row dict (needs
    id, company, role_title, jd_text, round_type, round_length_min,
    interviewer_title, recruiter_notes). Returns the brief, generating + caching
    on a miss. None on failure or an unusably empty brief."""
    interview_id = interview.get("id")
    if not interview_id or not resume_text.strip():
        return None
    lang = _resolve_lang(lang)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION, path=path)
        if cached is not None:
            return _row_to_brief(cached)

    if client.all_models_exhausted():
        return None

    brief = _generate(resume_text, interview, research or [], client, lang=lang)
    if brief is None or brief.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION,
                          brief.to_dict_for_cache(), model_used, path=path)
    stored = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION, path=path)
    return _row_to_brief(stored) if stored else brief


def read_cached_brief(
    interview_id: int, *, lang: Optional[str] = None, path=db.DB_PATH,
) -> Optional[Brief]:
    """Cache-only read — no client, no generation. The Brief screen's GET uses
    this to render an already-built brief (or redirect to the generating screen
    on a miss) without risking a synchronous LLM call on a page load."""
    if not interview_id:
        return None
    lang = _resolve_lang(lang)
    cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, PROMPT_VERSION, path=path)
    return _row_to_brief(cached) if cached is not None else None


def _generate(
    resume_text: str, interview: dict, research: list[dict], client: GeminiClient,
    *, lang: str,
) -> Optional[Brief]:
    prompt = _build_prompt(resume_text, interview, research, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return _parse_brief(raw)


def _build_prompt(resume_text: str, interview: dict, research: list[dict], *, lang: str) -> str:
    role = (interview.get("role_title") or "").strip() or "(unknown role)"
    company = (interview.get("company") or "").strip() or "(unknown company)"
    round_type = (interview.get("round_type") or "screening").strip()
    length = interview.get("round_length_min") or 45
    interviewer = (interview.get("interviewer_title") or "").strip() or "(not given)"
    notes = P.clip(interview.get("recruiter_notes") or "", P.MAX_NOTES_CHARS) or "(none)"
    jd = P.clip(interview.get("jd_text") or "", P.MAX_JD_CHARS)
    jd_block = jd if jd else "(not provided — base competencies on the role title and résumé)"
    resume = P.clip(resume_text, P.MAX_RESUME_CHARS)

    return f"""You are helping a candidate prepare for a job interview for the role of {role} at {company}.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Read the job description, company research, and résumé. Build an interview brief.

Do this:
1. Summarize the role in 2 sentences.
2. Summarize the company in 3 short bullets. Each bullet must cite the source URL it came from. If there is no research, return an empty list.
3. List the {MIN_COMPETENCIES} to {MAX_COMPETENCIES} competencies this interview will most likely test. Base them on the job description. Give each a stable id (c1, c2, …). For each one, say in one sentence what a strong answer shows.
4. For each competency, rate the candidate's résumé evidence: strong, solid, or needs_work. Quote the résumé item that supports it. If nothing supports it, use needs_work and evidence null.
5. List up to {MAX_GAPS} gaps. For each gap, give one concrete prep action and the competency id it belongs to (or null).
6. Based on the interviewer's title (if given) and the round type, list what this interviewer likely cares about in {MAX_LENS} bullets. If no title is given, base it on the round type only.
7. List up to {MAX_FRICTION} likely friction points (tough topics they may push on).
8. Write up to {MAX_CLARIFY_QUESTIONS} short CLARIFYING questions to ask the candidate about items ALREADY on the résumé that this interview will lean on. Ask HOW: the method or process they used, the tools, what they personally did, or how the action led to the result. Never ask for new achievements or new numbers. Address the candidate as "you"; one short sentence each; set competency_id. For each, write "example": a one-line first-person sample that shows the FORMAT of a good answer (e.g. "I pulled weekly SAP extracts into Power BI and reviewed variances every Monday"). The example only illustrates the format — generic wording, never facts from the résumé. If the résumé already explains the how, ask fewer.

Round type: {round_type}. Length: {length} minutes.
Interviewer title: {interviewer}
Recruiter notes: {notes}

Job description:
---
{jd_block}
---

Company research:
{P.format_research(research)}

Résumé:
---
{resume}
---

Return JSON with this exact schema — no prose before or after:
{{
  "role_summary": "string",
  "company_snapshot": [{{ "point": "string", "source_url": "string" }}],
  "competencies": [
    {{ "id": "c1", "name": "string", "what_good_looks_like": "string",
       "resume_match": "strong | solid | needs_work", "evidence": "string | null" }}
  ],
  "gaps": [{{ "competency_id": "c1 | null", "gap": "string", "action": "string" }}],
  "interviewer_lens": ["string"],
  "friction_points": ["string"],
  "clarify_questions": [{{ "question": "string", "example": "string", "competency_id": "c1 | null" }}]
}}"""


# ---------- parsing (defensive: keep only well-formed items) ----------

def _parse_brief(raw: Any) -> Brief:
    if not isinstance(raw, dict):
        return Brief()
    return Brief(
        role_summary=str(raw.get("role_summary", "")).strip(),
        company_snapshot=_parse_snapshot(raw.get("company_snapshot")),
        competencies=_parse_competencies(raw.get("competencies")),
        gaps=_parse_gaps(raw.get("gaps")),
        interviewer_lens=_parse_str_list(raw.get("interviewer_lens"), MAX_LENS),
        friction_points=_parse_str_list(raw.get("friction_points"), MAX_FRICTION),
        clarify_questions=_parse_clarify(raw.get("clarify_questions")),
    )


def _parse_clarify(items: Any) -> list[ClarifyQuestion]:
    """Keep non-blank questions, re-id f1..fN, cap. competency_id is validated
    against the brief by the caller's join (unknown ids are harmless here)."""
    out: list[ClarifyQuestion] = []
    if not isinstance(items, list):
        return out
    for it in items:
        q = str(it.get("question", "")).strip() if isinstance(it, dict) else str(it or "").strip()
        if not q:
            continue
        ex = str(it.get("example", "")).strip() if isinstance(it, dict) else ""
        cid = str(it.get("competency_id") or "").strip() if isinstance(it, dict) else ""
        out.append(ClarifyQuestion(id=f"f{len(out) + 1}", question=q, example=ex,
                                   competency_id=cid if cid and cid.lower() != "null" else None))
        if len(out) >= MAX_CLARIFY_QUESTIONS:
            break
    return out


def _parse_snapshot(items: Any) -> list[CompanyPoint]:
    out: list[CompanyPoint] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        point = str(it.get("point", "")).strip()
        if not point:
            continue
        url = str(it.get("source_url") or "").strip() or None
        out.append(CompanyPoint(point=point, source_url=url))
    return out


def _parse_competencies(items: Any) -> list[Competency]:
    """Keep well-formed competencies, re-id them c1..cN so the join key is
    always dense and stable even if the model skipped a number, and cap at
    MAX_COMPETENCIES. A competency with no name is dropped."""
    out: list[Competency] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        good = str(it.get("what_good_looks_like", "")).strip()
        if not name:
            continue
        cid = f"c{len(out) + 1}"
        evidence = it.get("evidence")
        evidence = str(evidence).strip() if evidence not in (None, "") else None
        out.append(Competency(
            id=cid, name=name, what_good_looks_like=good,
            resume_match=P.band_or_default(it.get("resume_match")),
            evidence=evidence,
        ))
        if len(out) >= MAX_COMPETENCIES:
            break
    return out


def _parse_gaps(items: Any) -> list[Gap]:
    out: list[Gap] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        gap = str(it.get("gap", "")).strip()
        action = str(it.get("action", "")).strip()
        if not gap or not action:
            continue
        cid = it.get("competency_id")
        cid = str(cid).strip() if cid not in (None, "") else None
        out.append(Gap(competency_id=cid, gap=gap, action=action))
        if len(out) >= MAX_GAPS:
            break
    return out


def _parse_str_list(items: Any, cap: int) -> list[str]:
    if not isinstance(items, list):
        return []
    out = [str(x).strip() for x in items if str(x).strip()]
    return out[:cap]
