"""The Get Ready toolkit in ONE call (ADR-057, REQ-041) — replaces the P2
questions / P3 story mapping / P4 answer cards chain.

Eduardo (2026-09-29): "todo este material debería venir desde que procesamos el
brief, nada de construir por capas — perdemos contexto, tokens y llamadas". The
three calls each re-sent the same brief + résumé and saw only a slice of the
picture (P4 answered questions it hadn't written, with stories it hadn't
picked). One call with the full context writes all of it consistently:

  - questions[] (8–10): the likely questions in interview flow order, each with
    why they ask it, one follow-up, the point to land and an answer SKELETON
    (ADR-058): bullets under fixed sections chosen by question type in code, in
    my first person, with a visible [[hint: …]] slot wherever the inputs don't
    say HOW — never generic filler;
  - stories[] (one per competency): the best Story Bank story for it (+ why and
    the angle for this role), or — when none fits — a STAR draft built from the
    résumé that the candidate can save to the bank;
  - questions_to_ask[] (3–4): questions for the end of the interview, each with
    why it's a good question and what asking it shows about me.

Inputs: the cached Brief (P1), the candidate's answers to the Brief's fact
questions ("facts" — the specifics the résumé lacked), the saved Story Bank and
the résumé. Cache in `prep_artifacts(interview, 'toolkit', lang, version)` with
version = PROMPT_VERSION + a fingerprint of brief/stories/facts, so any of them
changing is a miss, never stale. temperature=0.0. Joins are validated in code:
unknown competency ids are nulled, unknown story ids fall back to "no story".
"""
from __future__ import annotations

import hashlib
import re
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import brief as p1
from . import prompts as P

PROMPT_VERSION = "2026-10-01-toolkit-v4"
ARTIFACT_KIND = "toolkit"
FACTS_KIND = "facts"
FACTS_VERSION = "v2"   # v2 stores the question text with each answer

MIN_QUESTIONS = 8
MAX_QUESTIONS = 10
MAX_QUESTIONS_TO_ASK = 4
VALID_TYPES = ("opener", "behavioral", "approach", "situational", "technical")
DEFAULT_TYPE = "behavioral"

# Answer skeletons (ADR-058) — the SECTIONS are fixed in code per question type;
# the model only fills bullets. A "how do you approach…" question answered as a
# STAR narrative was the root of the vague cards (it never states the method).
FRAMES: dict[str, tuple[str, ...]] = {
    "approach":    ("approach", "example", "result"),      # how do you…?  method first
    "situational": ("approach", "example", "result"),      # what would you do if…?
    "behavioral":  ("situation", "task", "action", "result"),  # tell me about a time… (full STAR)
    "opener":      ("now", "before", "why_here"),          # tell me about yourself / why us
    "technical":   ("what", "how_i_used_it", "example"),
}
MAX_POINTS = 3

# Filler that sounds complete but says nothing — the phrases Eduardo flagged
# ("strict financial oversight", "rigorous tracking") and their kin. Detected
# in code; a card containing any is marked needs_input.
FILLER_PHRASES = (
    "strict oversight", "strict financial oversight", "rigorous", "rigorously",
    "effectively", "closely tracked", "closely monitored", "ensured alignment",
    "ensure alignment", "best practices", "proven track record", "robust",
    "seamless", "leveraged", "meticulous", "various stakeholders",
    "de manera efectiva", "riguros", "supervisión estricta", "mejores prácticas",
    # flagged by the interviewer judge on 2026-10-01
    "actionable insights", "informed decisions", "trusted partnerships", "drive results",
    "value-add", "synergy", "strategic decisions", "maintained budget performance",
    "decisiones informadas", "insights accionables",
)
HINT_OPEN, HINT_CLOSE = "[[hint:", "]]"


@dataclass
class ToolkitQuestion:
    """A likely question + my answer. Carries the P2 Question fields (id, text,
    type, competency_id, why_they_ask, follow_up) so Practice keeps working."""
    id: str
    text: str
    type: str
    competency_id: Optional[str]
    why_they_ask: str = ""
    follow_up: str = ""
    point_to_land: str = ""
    # [{section, points: [str]}] — points may carry [[hint: …]] slots
    frame: list[dict] = field(default_factory=list)
    needs_input: bool = False          # a hint slot or a filler phrase is present
    filler: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StoryPick:
    """One competency's story. Same attribute names as the old P3 Mapping
    (competency_id, story_id, why_it_fits, angle_for_this_role) so readiness and
    the live coach's cues read it unchanged. `draft` = a STAR drafted from the
    résumé when no bank story fits (story_id None)."""
    competency_id: str
    story_id: Optional[str] = None
    why_it_fits: Optional[str] = None
    angle_for_this_role: Optional[str] = None
    draft: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AskQuestion:
    question: str
    why: str = ""
    shows: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Toolkit:
    questions: list[ToolkitQuestion] = field(default_factory=list)
    stories: list[StoryPick] = field(default_factory=list)
    questions_to_ask: list[AskQuestion] = field(default_factory=list)
    created_at: str = ""

    def is_empty(self) -> bool:
        return not self.questions

    def to_dict_for_cache(self) -> dict[str, Any]:
        return {
            "questions": [q.to_dict() for q in self.questions],
            "stories": [s.to_dict() for s in self.stories],
            "questions_to_ask": [a.to_dict() for a in self.questions_to_ask],
        }


# ---------- facts: the candidate's answers to the Brief's fact questions ----------

def read_facts(interview_id: int, *, path=db.DB_PATH) -> dict[str, str]:
    """{question_text: answer} — only non-blank answers. Keyed by the question's
    TEXT, not its f-id, so a regenerated Brief (new questions re-using f1..fN)
    can never attach an old answer to a different question. {} when none."""
    row = db.get_prep_artifact(interview_id, FACTS_KIND, "", FACTS_VERSION, path=path)
    a = (row or {}).get("artifact")
    return ({str(k): str(v).strip() for k, v in a.items() if not str(k).startswith("__") and str(v).strip()}
            if isinstance(a, dict) else {})


def _asked_key(questions: list[str]) -> str:
    return hashlib.sha1("\n".join(sorted(q.strip() for q in questions)).encode("utf-8")).hexdigest()[:12]


def facts_submitted(interview_id: int, questions: list[str], *, path=db.DB_PATH) -> bool:
    """True once the candidate answered OR skipped THIS set of Clarify questions.
    Keyed by the questions asked, not just "a row exists": answers given to an
    older set (a regenerated Brief) must not skip the step — that bug built the
    cards before Eduardo saw the new questions (2026-09-29)."""
    row = db.get_prep_artifact(interview_id, FACTS_KIND, "", FACTS_VERSION, path=path)
    a = (row or {}).get("artifact")
    if not isinstance(a, dict):
        return False
    if "__asked__" in a:
        # done = this exact set was shown AND either answered or explicitly skipped
        # (a marker with no answers and no skip is the state the old skip bug left)
        answered = any(not str(k).startswith("__") and str(v).strip() for k, v in a.items())
        return a["__asked__"] == _asked_key(questions) and (answered or a.get("__skipped__") == "1")
    # rows saved before the marker existed: answered if they answer THESE questions
    return any(q in a for q in questions)


COMP_PREFIX = "__comp::"


def fact_competencies(interview_id: int, *, path=db.DB_PATH) -> dict[str, str]:
    """{fact key: competency id} for gap answers — which competency a card gap
    belonged to when it was answered (card texts change on a rewrite, so the key
    alone can't be re-joined later). Used to pre-fill a story's Strengthen."""
    row = db.get_prep_artifact(interview_id, FACTS_KIND, "", FACTS_VERSION, path=path)
    a = (row or {}).get("artifact")
    return ({k[len(COMP_PREFIX):]: str(v) for k, v in a.items() if str(k).startswith(COMP_PREFIX)}
            if isinstance(a, dict) else {})


def save_facts(interview_id: int, answers: dict[str, str], *, asked: Optional[list[str]] = None,
               skipped: bool = False, comps: Optional[dict[str, str]] = None, path=db.DB_PATH) -> None:
    """`answers` = {question_text: answer}; blank answers dropped. `asked` = the
    question set shown (answered or skipped) — see facts_submitted. `comps` =
    {gap key: competency id}, merged with the ones already stored (kept)."""
    clean = {str(k).strip(): str(v).strip()[:P.MAX_NOTES_CHARS]
             for k, v in answers.items() if str(k).strip() and str(v).strip()}
    for k, c in {**fact_competencies(interview_id, path=path), **(comps or {})}.items():
        if c and k in clean:
            clean[COMP_PREFIX + k] = c
    if asked is not None:
        clean["__asked__"] = _asked_key(asked)
    if skipped:
        clean["__skipped__"] = "1"
    db.save_prep_artifact(interview_id, FACTS_KIND, "", FACTS_VERSION, clean, path=path)


# ---------- cache keys ----------

def _resolve_lang(lang: Optional[str]) -> str:
    return lang if lang is not None else get_output_language()


def _fingerprint(brief: dict, stories: list[dict], facts: dict[str, str]) -> str:
    comps = sorted((str(c.get("id", "")), str(c.get("name", "")))
                   for c in (brief.get("competencies") or []) if isinstance(c, dict))
    story_rows = sorted(
        ({k: str(s.get(k, "")) for k in ("id", "title", "situation", "task", "action", "result", "metric")}
         for s in stories if isinstance(s, dict)),
        key=lambda r: r["id"],
    )
    blob = json.dumps({"r": str(brief.get("role_summary", "")), "c": comps,
                       "s": story_rows, "f": sorted(facts.items())},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _cache_version(brief: dict, stories: list[dict], facts: dict[str, str]) -> str:
    return f"{PROMPT_VERSION}:{_fingerprint(brief, stories, facts)}"


def _row_to_toolkit(row: dict) -> Toolkit:
    tk = _parse_toolkit(row.get("artifact") or {}, valid_comps=None, valid_stories=None)
    tk.created_at = row.get("created_at", "")
    return tk


# ---------- entry points ----------

def read_cached_toolkit(
    interview_id: int, stories: list[dict], *, lang: Optional[str] = None, path=db.DB_PATH,
) -> Optional[Toolkit]:
    """Cache-only read (never generates) — for Practice setup, readiness and the
    live coach. None when the toolkit hasn't been built for the current brief /
    Story Bank / facts."""
    lang = _resolve_lang(lang)
    brief = p1.read_cached_brief(interview_id, lang=lang, path=path)
    if brief is None or brief.is_empty():
        return None
    version = _cache_version(brief.to_dict_for_cache(), stories, read_facts(interview_id, path=path))
    row = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
    return _row_to_toolkit(row) if row else None


def read_cached_mapping(
    interview_id: int, stories: list[dict], *, lang: Optional[str] = None, path=db.DB_PATH,
) -> Optional[list[StoryPick]]:
    """The per-competency story picks (old P3 contract) from the cached toolkit."""
    tk = read_cached_toolkit(interview_id, stories, lang=lang, path=path)
    return tk.stories if tk else None


def get_or_generate_toolkit(
    interview: dict,
    brief: dict,
    stories: list[dict],
    resume_text: str,
    client: GeminiClient,
    *,
    lang: Optional[str] = None,
    use_cache: bool = True,
    path=db.DB_PATH,
) -> Optional[Toolkit]:
    """Cache-aware entry point. `brief` = P1's cached dict; `stories` = the saved
    Story Bank. Facts are read from the interview. Returns the toolkit,
    generating + caching on a miss. None on failure, an empty result, or no
    competencies / résumé."""
    interview_id = interview.get("id")
    if not interview_id or not resume_text.strip() or not brief.get("competencies"):
        return None
    lang = _resolve_lang(lang)
    facts = read_facts(interview_id, path=path)
    version = _cache_version(brief, stories, facts)

    if use_cache:
        cached = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
        if cached is not None:
            return _row_to_toolkit(cached)

    if client.all_models_exhausted():
        return None

    prompt = _build_prompt(interview, brief, stories, facts, resume_text, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    tk = _parse_toolkit(
        raw,
        valid_comps={str(c.get("id", "")) for c in brief.get("competencies") or [] if isinstance(c, dict)},
        valid_stories={str(s.get("id", "")) for s in stories if isinstance(s, dict)},
        all_comps=[str(c.get("id", "")) for c in brief.get("competencies") or [] if isinstance(c, dict)],
    )
    if tk.is_empty():
        return None

    model_used = client.last_model_used or client.model_name or ""
    db.save_prep_artifact(interview_id, ARTIFACT_KIND, lang, version,
                          tk.to_dict_for_cache(), model_used, path=path)
    stored = db.get_prep_artifact(interview_id, ARTIFACT_KIND, lang, version, path=path)
    return _row_to_toolkit(stored) if stored else tk


# ---------- prompt ----------

def _facts_block(facts: dict[str, str]) -> str:
    lines = [f"- Q: {q}\n  A (my own words): {ans}" for q, ans in facts.items() if ans]
    return "\n".join(lines) if lines else "(none given — rely on the résumé only)"


def _brief_block(brief: dict) -> str:
    keep = {
        "role_summary": brief.get("role_summary", ""),
        "company_snapshot": [p.get("point", "") for p in brief.get("company_snapshot") or [] if isinstance(p, dict)],
        "competencies": [
            {k: c.get(k) for k in ("id", "name", "what_good_looks_like", "resume_match", "evidence")}
            for c in brief.get("competencies") or [] if isinstance(c, dict)],
        "gaps": brief.get("gaps") or [],
        "interviewer_lens": brief.get("interviewer_lens") or [],
        "friction_points": brief.get("friction_points") or [],
    }
    return json.dumps(keep, ensure_ascii=False, indent=2)


def _build_prompt(interview: dict, brief: dict, stories: list[dict], facts: dict[str, str],
                  resume_text: str, *, lang: str) -> str:
    company = (interview.get("company") or "").strip() or "(unknown company)"
    role = (interview.get("role_title") or "").strip() or "(unknown role)"
    round_type = (interview.get("round_type") or "screening").strip()
    jd = P.clip(interview.get("jd_text") or "", P.MAX_JD_CHARS)
    jd_block = jd if jd else "(not provided — use the role title and the brief)"
    resume = P.clip(resume_text, P.MAX_RESUME_CHARS)

    return f"""You are my interview coach. I have a {round_type} interview for {role} at {company}. Build my Get Ready toolkit in one pass, using everything below.

{P.RULE_BLOCK}
- Write AS ME, in the first person ("I led…", "At CRA I…"). Never use my name, never "the candidate", never "he/she".
- Structure what is already in my résumé and my answers — never add new achievements, employers, tools or numbers.
- Be concrete: use the real employers, tools, numbers and results from my résumé and from MY ANSWERS below. MY ANSWERS are authoritative — prefer them over the résumé.
- Keep every number with EXACTLY the meaning it has in my words or my résumé. Never add numbers together, never turn a number into a share of something else (no "X% of the budget" unless I said so), never re-derive or round. Example: if I wrote "the forecast savings were 15% and I delivered an extra 10%", say exactly that — not "25% of the budget".
- If my wording is ambiguous, stay close to my words instead of reinterpreting them.
- If there is no evidence for something, do not invent it — answer honestly with the closest real experience and how it transfers.

{language_instruction(lang)}

Task:
A. QUESTIONS — write {MIN_QUESTIONS} to {MAX_QUESTIONS} questions this interview will most likely include, in the order a real interview flows.
   - Mix for the round type: screening = mostly openers and motivation + 1-2 behavioral; behavioral = one per competency; technical = role knowledge + 1-2 behavioral; case = situational/problem-solving; hiring_manager = behavioral + situational + one "first 90 days"; final_panel = a harder mix.
   - type: "opener" (about me / why here), "behavioral" (tell me about a time…), "approach" (how do you…? / what is your process for…?), "situational" (what would you do if…?), "technical" (role knowledge).
   - competency_id (from the brief, or null for an opener), why they ask it (one sentence), one likely follow-up, and "point_to_land" (one short line: what the interviewer must remember).
   - "frame": an answer SKELETON — NOT prose. Use EXACTLY these sections for the type, in this order, 1 to {MAX_POINTS} bullets each, each bullet at most 14 words, in my first person:
       approach / situational → "approach" (the concrete method or steps I use — name them), "example" (one real case from my résumé or stories), "result"
       behavioral → "situation", "task" (what I was responsible for / the goal — one sentence), "action" (what I personally did, how), "result"
       opener → "now", "before", "why_here"
       technical → "what", "how_i_used_it", "example"
   - The skeleton must ANSWER THE QUESTION ASKED: if it asks "how", the first section says how.
   - Write each bullet as a FULL SENTENCE so that a section's bullets, joined together, read as one natural spoken paragraph (it is shown that way).
   - When the inputs don't say HOW I did something (the method, the tool, my personal step, how the action produced the result), DO NOT fill the gap with generic words. Write a hint slot instead: [[hint: what to add — e.g. a concrete example]]. Example bullet: "I track opex and capex against forecast [[hint: your cadence/tool — e.g. monthly variance review in Power BI]]".
   - Never use these filler words: strict oversight, rigorous, effectively, closely tracked, closely monitored, ensured alignment, best practices, proven track record, robust, seamless, leveraged, actionable insights, informed decisions, trusted partnerships, drive results.
B. STORIES — for EVERY competency in the brief:
   - pick the best story from my Story Bank (story_id), say in one sentence why it fits and one sentence how to angle it for this role;
   - if no saved story fits, set story_id null and write "draft": a STAR story from my résumé (and my answers) for this competency — title, situation, task, action (what I did, with "I"), result, metric (a number only if it is in the inputs, else null). Where the inputs don't say HOW (the method, or how the action produced the result), put a [[hint: …]] slot in that field instead of generic words. Do not repeat the metric inside the result. If the résumé has nothing usable, set draft null.
C. QUESTIONS TO ASK — {MAX_QUESTIONS_TO_ASK - 1} to {MAX_QUESTIONS_TO_ASK} questions I can ask at the end. Keep them SHORT and plain: one sentence, at most 15 words, easy to remember under pressure — smart, not complicated. For each: why it is a good question (one short sentence), and "shows" = what asking it shows about me (2-4 words, e.g. "strategic thinking").

The brief (competencies use these ids):
{_brief_block(brief)}

MY CLARIFICATIONS — how I did things the résumé only names (authoritative — keep their meaning exactly; use them to fill the "how"):
{_facts_block(facts)}

My Story Bank (use these story ids):
{P.format_stories(stories)}

Job description:
---
{jd_block}
---

My résumé:
---
{resume}
---

Return JSON with this exact schema — no prose before or after:
{{
  "questions": [
    {{ "text": "string", "type": "opener | behavioral | approach | situational | technical", "competency_id": "c1 | null",
       "why_they_ask": "string", "follow_up": "string", "point_to_land": "string",
       "frame": [{{ "section": "approach", "points": ["string"] }}] }}
  ],
  "stories": [
    {{ "competency_id": "c1", "story_id": "12 | null", "why_it_fits": "string | null",
       "angle_for_this_role": "string | null",
       "draft": {{ "title": "string", "situation": "string", "task": "string", "action": "string",
                  "result": "string", "metric": "string | null" }} }}
  ],
  "questions_to_ask": [{{ "question": "string", "why": "string", "shows": "string" }}]
}}"""


# ---------- parsing (defensive; joins validated in code) ----------

def _s(v: Any) -> str:
    return str(v).strip() if v not in (None,) else ""


def _opt(v: Any) -> Optional[str]:
    t = _s(v)
    return t if t and t.lower() != "null" else None


def _parse_toolkit(raw: Any, *, valid_comps: Optional[set[str]], valid_stories: Optional[set[str]],
                   all_comps: Optional[list[str]] = None) -> Toolkit:
    if not isinstance(raw, dict):
        return Toolkit()
    return Toolkit(
        questions=_parse_questions(raw.get("questions"), valid_comps),
        stories=_parse_stories(raw.get("stories"), valid_comps, valid_stories, all_comps),
        questions_to_ask=_parse_ask(raw.get("questions_to_ask")),
    )


def _parse_questions(items: Any, valid_comps: Optional[set[str]]) -> list[ToolkitQuestion]:
    """Re-id q1..qN (dense, stable order — the join key for card reviews and
    Practice), drop blank text, coerce unknown types, null unknown competencies.
    The cache-read path (valid_comps None) trusts stored ids."""
    out: list[ToolkitQuestion] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        text = _s(it.get("text"))
        if not text:
            continue
        qtype = _s(it.get("type")).lower()
        if qtype not in VALID_TYPES:
            qtype = DEFAULT_TYPE
        cid = _opt(it.get("competency_id"))
        if cid is not None and valid_comps is not None and cid not in valid_comps:
            cid = None
        qid = _s(it.get("id")) if valid_comps is None and _s(it.get("id")) else f"q{len(out) + 1}"
        frame = _parse_frame(it.get("frame"), qtype)
        filler = find_filler(" ".join(pt for sec in frame for pt in sec["points"]))
        has_hint = any(HINT_OPEN in pt for sec in frame for pt in sec["points"])
        out.append(ToolkitQuestion(
            id=qid, text=text, type=qtype, competency_id=cid,
            why_they_ask=_s(it.get("why_they_ask")), follow_up=_s(it.get("follow_up")),
            point_to_land=_s(it.get("point_to_land")),
            frame=frame, filler=filler, needs_input=bool(filler) or has_hint or not frame,
        ))
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def _parse_frame(items: Any, qtype: str) -> list[dict]:
    """Keep only the sections the type's template allows, in template order;
    ≤ MAX_POINTS non-blank bullets each. Sections the model invented are
    dropped; missing ones are simply absent (the card is then needs_input)."""
    allowed = FRAMES.get(qtype, FRAMES[DEFAULT_TYPE])
    by_sec: dict[str, list[str]] = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        sec = _s(it.get("section")).lower()
        if sec not in allowed or sec in by_sec:
            continue
        pts = it.get("points")
        pts = [_s(x) for x in (pts if isinstance(pts, list) else [pts]) if _s(x)]
        if pts:
            by_sec[sec] = pts[:MAX_POINTS]
    return [{"section": sec, "points": by_sec[sec]} for sec in allowed if sec in by_sec]


def find_filler(text: str) -> list[str]:
    """Banned filler phrases present in `text` (case-insensitive), in list order."""
    low = (text or "").lower()
    return [f for f in FILLER_PHRASES if f in low]


def split_hints(text: str) -> list[tuple[str, str]]:
    """Split a bullet into [('t', text) | ('h', hint)] segments for rendering.
    An unclosed [[hint: is treated as plain text (never swallow content)."""
    out: list[tuple[str, str]] = []
    rest = text or ""
    while True:
        i = rest.find(HINT_OPEN)
        j = rest.find(HINT_CLOSE, i + len(HINT_OPEN)) if i >= 0 else -1
        if i < 0 or j < 0:
            if rest:
                out.append(("t", rest))
            return out
        if rest[:i]:
            out.append(("t", rest[:i]))
        hint = rest[i + len(HINT_OPEN):j].strip()
        if hint:
            out.append(("h", hint))
        rest = rest[j + len(HINT_CLOSE):]


def gap_key(card_text: str, hint: str) -> str:
    """The facts key for a ✎ gap answer — shared by the card's inline field and
    the check-in, so both fill the same gap."""
    return f"{card_text} — {hint}"


_EG = re.compile(r"\s*[—–-]?\s*\(?\b(?:e\.g\.|p\. ?ej\.|por ejemplo|for example)\s*", re.IGNORECASE)


def card_gaps(tk: "Toolkit") -> list[dict]:
    """Every ✎ slot on the cards as a check-in question (2026-10-01: "Improve my
    answers · 9 gaps" opened the 3 old questions, so the count meant nothing).
    → [{key, card, question, example}], de-duplicated, in card order. The hint's
    "e.g. …" tail becomes the placeholder example."""
    out, seen = [], set()
    for q in tk.questions:
        for sec in q.frame:
            for pt in sec.get("points") or []:
                for kind, val in split_hints(str(pt)):
                    if kind != "h":
                        continue
                    key = gap_key(q.text, val)
                    if key in seen:
                        continue
                    seen.add(key)
                    parts = _EG.split(val, maxsplit=1)
                    head = parts[0].strip(" —–-").strip()
                    example = parts[1].strip(" )") if len(parts) > 1 else ""
                    out.append({"key": key, "card": q.text,
                                "question": (head[:1].upper() + head[1:]) if head else val,
                                "example": example})
    return out


def _parse_draft(d: Any) -> Optional[dict]:
    if not isinstance(d, dict):
        return None
    draft = {k: _s(d.get(k)) for k in ("title", "situation", "task", "action", "result")}
    draft["metric"] = _opt(d.get("metric"))
    return draft if (draft["title"] or draft["action"]) else None


def _parse_stories(items: Any, valid_comps: Optional[set[str]], valid_stories: Optional[set[str]],
                   all_comps: Optional[list[str]]) -> list[StoryPick]:
    """One row per competency: unknown/duplicate competencies dropped, an
    unknown story id falls back to 'no story' (its why/angle dropped), a draft
    is kept only when there is no story. On generation, every brief competency
    gets a row (missing ones become an empty gap) so the tab never skips one."""
    out: list[StoryPick] = []
    seen: set[str] = set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        cid = _s(it.get("competency_id"))
        if not cid or cid in seen or (valid_comps is not None and cid not in valid_comps):
            continue
        seen.add(cid)
        sid = _opt(it.get("story_id"))
        if sid is not None and valid_stories is not None and sid not in valid_stories:
            sid = None
        pick = StoryPick(competency_id=cid, story_id=sid)
        if sid:
            pick.why_it_fits = _opt(it.get("why_it_fits"))
            pick.angle_for_this_role = _opt(it.get("angle_for_this_role"))
        else:
            pick.draft = _parse_draft(it.get("draft")) if valid_comps is not None else (
                it.get("draft") if isinstance(it.get("draft"), dict) else None)
        out.append(pick)
    for cid in all_comps or []:
        if cid not in seen:
            out.append(StoryPick(competency_id=cid))
    return out


def _parse_ask(items: Any) -> list[AskQuestion]:
    out: list[AskQuestion] = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            q = _s(it.get("question"))
            if q:
                out.append(AskQuestion(question=q, why=_s(it.get("why")), shows=_s(it.get("shows"))))
        elif _s(it):
            out.append(AskQuestion(question=_s(it)))
        if len(out) >= MAX_QUESTIONS_TO_ASK:
            break
    return out
