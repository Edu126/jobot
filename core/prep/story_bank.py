"""Story Bank generation (ADR-050, REQ-041 / D4, Flow B) — the account-level
STAR-story assets P3 maps to interview competencies.

  - P5 `draft_stories_from_resume`: 4–6 STAR drafts mined from the résumé, each
    with competency tags and — where the résumé is silent — a question to ask
    the candidate (never an invented number). The user accepts / edits / discards.
  - P6 `story_from_voice`: turns a 1–2 minute spoken story into one STAR story,
    keeping the candidate's own facts and flagging a missing result / metric /
    unclear personal role.
  - `strength_check`: the badge shown in the bank (Strong / Needs a result /
    Needs a number / Clarify your role), computed in CODE from the story's
    fields — deterministic, so it stays honest after the user edits, exactly
    like delivery metrics are computed in code, not asked of the model.

Unlike P1–P4 these are account-level and NOT interview-cached: they generate
drafts that become `stories` rows (db.create_story). No prep_artifacts caching.
temperature=0.0. Never invents facts or numbers (GOV-005).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError
from core.settings import get_output_language, language_instruction

from . import prompts as P

P5_PROMPT_VERSION = "2026-09-21-draft-stories-v1"
P6_PROMPT_VERSION = "2026-09-21-voice-star-v1"
REFINE_PROMPT_VERSION = "2026-09-30-refine-star-v1"

MIN_DRAFTS = 4
MAX_DRAFTS = 6
MAX_TAGS = 3
MAX_TRANSCRIPT_CHARS = 6000

# The tag vocabulary P5/P6 draw from — the competencies structured interviews
# most often test (D4). Kept here so drafts tag consistently even before an
# interview's own competency list exists (the bank is account-level, P1 is not).
DEFAULT_COMPETENCY_TAGS = (
    "Leadership", "Stakeholder management", "Problem solving", "Communication",
    "Ownership", "Collaboration", "Technical depth", "Data analysis",
    "Conflict resolution", "Adaptability", "Execution & delivery", "Customer focus",
)

# strength_check flag → the badge shown in the Story Bank list (B1).
BADGE_LABELS = {
    "strong": "Strong",
    "needs_result": "Needs a result",
    "needs_number": "Needs a number",
    "needs_owner": "Clarify your role",
    "needs_how": "Explain how",
}

_HAS_NUMBER = re.compile(r"\d")
_WE_WORDS = re.compile(r"\b(we|our|ours|us)\b", re.IGNORECASE)
_I_WORDS = re.compile(r"\b(i|i'm|i've|i'd|i'll|my|mine|myself)\b", re.IGNORECASE)
# ADR-058: an Action that names WHAT without HOW ("Created Power BI dashboards to
# support data preparation") — short and with no method connector. The how is
# what makes a story credible and is exactly what the résumé leaves out.
_HOW_WORDS = re.compile(
    r"\b(by|using|through|via|with|so that|which|automat\w*|mediante|usando|con|a trav[eé]s|para que)\b",
    re.IGNORECASE)
_HOW_MIN_WORDS = 18


@dataclass
class StoryDraft:
    title: str = ""
    situation: str = ""
    task: str = ""
    action: str = ""
    result: Optional[str] = None
    metric: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    questions_for_candidate: list[str] = field(default_factory=list)  # P5
    strength: Optional[str] = None                                    # P6 (model's read)
    strength_reason: Optional[str] = None                             # P6
    follow_up_question: Optional[str] = None                          # P6

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------- code-side strength check (deterministic, GOV honesty) ----------

def strength_check(story: dict) -> dict:
    """Flag a story's weaknesses from its fields — no LLM. Returns
    {flags: [...], badge: "<key>", badge_label: "..."}. Flags:
      - missing_result: the Result is blank;
      - missing_metric: no number anywhere in result/metric;
      - unclear_personal_role: the Action is 'we' language with no clear 'I';
      - missing_how: a short Action with no method ("by / using / through…").
    Badge is the single most important flag (result > owner > number), or
    'strong' when clean. Computed on read so it never drifts from edits."""
    result = str(story.get("result") or "").strip()
    metric = str(story.get("metric") or "").strip()
    action = str(story.get("action") or "").strip()

    flags: list[str] = []
    if not result:
        flags.append("missing_result")
    if not (_HAS_NUMBER.search(metric) or _HAS_NUMBER.search(result)):
        flags.append("missing_metric")
    if action and _WE_WORDS.search(action) and not _I_WORDS.search(action):
        flags.append("unclear_personal_role")
    if action and len(action.split()) < _HOW_MIN_WORDS and not _HOW_WORDS.search(action):
        flags.append("missing_how")

    if "missing_result" in flags:
        badge = "needs_result"
    elif "unclear_personal_role" in flags:
        badge = "needs_owner"
    elif "missing_how" in flags:
        badge = "needs_how"
    elif "missing_metric" in flags:
        badge = "needs_number"
    else:
        badge = "strong"
    return {"flags": flags, "badge": badge, "badge_label": BADGE_LABELS[badge]}


# ---------- P5: draft stories from the résumé ----------

def draft_stories_from_resume(
    resume_text: str,
    client: GeminiClient,
    *,
    competency_tags: Optional[tuple[str, ...]] = None,
    lang: Optional[str] = None,
) -> list[StoryDraft]:
    """Mine 4–6 STAR drafts from the résumé (P5). Returns drafts for the
    accept/edit/discard screen — the caller persists chosen ones via
    db.create_story(status='draft' or 'saved'). Empty list on failure or a
    résumé with nothing story-worthy."""
    if not resume_text.strip() or client.all_models_exhausted():
        return []
    lang = lang if lang is not None else get_output_language()
    tags = competency_tags or DEFAULT_COMPETENCY_TAGS
    prompt = _build_p5_prompt(P.clip(resume_text, P.MAX_RESUME_CHARS), tags, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return []
    items = raw.get("stories") if isinstance(raw, dict) else None
    return _parse_drafts(items, valid_tags=set(tags))


def _build_p5_prompt(resume: str, tags: tuple[str, ...], *, lang: str) -> str:
    tag_list = ", ".join(tags)
    return f"""You are helping a candidate build a bank of STAR interview stories from their résumé.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Draft STAR stories from the candidate's résumé.

Do this:
1. Pick the {MIN_DRAFTS} to {MAX_DRAFTS} résumé items with the most story potential (clear actions, results, or challenges).
2. For each, draft Situation, Task, Action, Result using only what the résumé says.
3. Do not invent numbers or details. If the result or a metric is missing, set it to null and add a short question to ask the candidate.
4. Suggest 1 to {MAX_TAGS} competency tags for each, chosen from this list: {tag_list}

Résumé:
---
{resume}
---

Return JSON with this exact schema — no prose before or after:
{{
  "stories": [
    {{ "title": "string", "situation": "string", "task": "string", "action": "string",
       "result": "string | null", "metric": "string | null",
       "tags": ["string"], "questions_for_candidate": ["string"] }}
  ]
}}"""


def _parse_drafts(items: Any, *, valid_tags: set[str]) -> list[StoryDraft]:
    """Keep drafts with at least a title and an action. Tags are filtered to the
    known vocabulary (case-insensitive) so the bank stays taggable; result/metric
    stay None when the model couldn't ground them (never invented)."""
    out: list[StoryDraft] = []
    if not isinstance(items, list):
        return out
    lower = {t.lower(): t for t in valid_tags}
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title", "")).strip()
        action = str(it.get("action", "")).strip()
        if not title or not action:
            continue
        out.append(StoryDraft(
            title=title,
            situation=str(it.get("situation", "")).strip(),
            task=str(it.get("task", "")).strip(),
            action=action,
            result=_none_or_str(it.get("result")),
            metric=_none_or_str(it.get("metric")),
            tags=_clean_tags(it.get("tags"), lower),
            questions_for_candidate=_str_list(it.get("questions_for_candidate"), 3),
        ))
        if len(out) >= MAX_DRAFTS:
            break
    return out


# ---------- P6: voice dump → STAR ----------

def story_from_voice(
    transcript: str,
    client: GeminiClient,
    *,
    competency_tags: Optional[tuple[str, ...]] = None,
    lang: Optional[str] = None,
) -> Optional[StoryDraft]:
    """Turn a spoken story (transcript) into one STAR story (P6). Keeps the
    candidate's facts, cleans wording, flags a missing result/metric/unclear
    role and asks one follow-up. None on failure or an empty transcript."""
    if not transcript.strip() or client.all_models_exhausted():
        return None
    lang = lang if lang is not None else get_output_language()
    tags = competency_tags or DEFAULT_COMPETENCY_TAGS
    prompt = _build_p6_prompt(P.clip(transcript, MAX_TRANSCRIPT_CHARS), tags, lang=lang)
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    return _parse_voice(raw, valid_tags=set(tags))


def _build_p6_prompt(transcript: str, tags: tuple[str, ...], *, lang: str) -> str:
    tag_list = ", ".join(tags)
    return f"""You are helping a candidate turn a spoken story into a polished STAR interview story.

{P.RULE_BLOCK}

{language_instruction(lang)}

Task: Turn the candidate's spoken story into a STAR story.

Do this:
1. Read the transcript. Extract Situation, Task, Action, Result.
2. Keep the candidate's own facts. Clean up the wording. Do not add anything they didn't say.
3. Make the Action about what the candidate did ("I"), not the team ("we"). If it's unclear what they did personally, flag it.
4. If the result or a metric is missing, set it to null and write one follow-up question.
5. Rate the story: strong, solid, or needs_work, with one sentence explaining why.
6. Suggest 1 to {MAX_TAGS} competency tags from this list: {tag_list}

Transcript:
---
{transcript}
---

Return JSON with this exact schema — no prose before or after:
{{
  "title": "string", "situation": "string", "task": "string", "action": "string",
  "result": "string | null", "metric": "string | null", "tags": ["string"],
  "strength": "strong | solid | needs_work", "strength_reason": "string",
  "flags": ["missing_result | missing_metric | unclear_personal_role"],
  "follow_up_question": "string | null"
}}"""


def _parse_voice(raw: Any, *, valid_tags: set[str]) -> Optional[StoryDraft]:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title", "")).strip()
    action = str(raw.get("action", "")).strip()
    if not title and not action:
        return None
    lower = {t.lower(): t for t in valid_tags}
    return StoryDraft(
        title=title or "Untitled story",
        situation=str(raw.get("situation", "")).strip(),
        task=str(raw.get("task", "")).strip(),
        action=action,
        result=_none_or_str(raw.get("result")),
        metric=_none_or_str(raw.get("metric")),
        tags=_clean_tags(raw.get("tags"), lower),
        strength=P.band_or_default(raw.get("strength")) if raw.get("strength") else None,
        strength_reason=_none_or_str(raw.get("strength_reason")),
        follow_up_question=_none_or_str(raw.get("follow_up_question")),
    )


# ---------- Strengthen: refine a saved story with the candidate's answers ----------

# One clarifying question per strength flag (code, no LLM) — the "Strengthen"
# screen asks only these. i18n keys: prep2.strengthen.q.<flag> / .eg.<flag>.
STRENGTHEN_FLAGS = ("missing_how", "unclear_personal_role", "missing_result", "missing_metric")


def refine_story(
    story: dict, answers: dict[str, str], client: GeminiClient, *, lang: Optional[str] = None,
) -> Optional[StoryDraft]:
    """Rewrite a saved STAR story using ONLY the story itself + the candidate's
    answers to the Strengthen questions (ADR-058). Never adds facts, numbers or
    tools they didn't give; keeps every number's meaning; the metric appears
    once. Returns a preview draft (the route saves it only on confirm). None on
    failure or when there are no answers."""
    answers = {k: str(v).strip() for k, v in (answers or {}).items() if str(v).strip()}
    if not answers or client.all_models_exhausted():
        return None
    lang = lang if lang is not None else get_output_language()
    star = "\n".join(f"{k}: {str(story.get(k) or '').strip() or '(empty)'}"
                     for k in ("title", "situation", "task", "action", "result", "metric"))
    qa = "\n".join(f"- {k}: {v}" for k, v in answers.items())
    prompt = f"""You are helping a candidate strengthen one STAR interview story.

{P.RULE_BLOCK}
- Use ONLY the story and the candidate's answers below. Do not add employers, tools, numbers or results they did not give.
- Keep every number with exactly the meaning it has. Never add numbers together or re-derive them.
- Action: what the candidate personally did and HOW (the method, tools, steps), with "I".
- Result: what changed, and how the action caused it. Put the metric in the Result once — do not repeat it elsewhere.
- Keep it short: each field 1-2 sentences.

{language_instruction(lang)}

The story now:
{star}

The candidate's answers (flag → answer):
{qa}

Return JSON with this exact schema — no prose before or after:
{{ "title": "string", "situation": "string", "task": "string", "action": "string", "result": "string", "metric": "string | null" }}"""
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (QuotaExhaustedError, GeminiError):
        return None
    if not isinstance(raw, dict) or not str(raw.get("action", "")).strip():
        return None
    return StoryDraft(
        title=str(raw.get("title") or story.get("title") or "").strip(),
        situation=str(raw.get("situation", "")).strip(),
        task=str(raw.get("task", "")).strip(),
        action=str(raw.get("action", "")).strip(),
        result=_none_or_str(raw.get("result")),
        metric=_none_or_str(raw.get("metric")),
        tags=list(story.get("tags") or []),
    )


# ---------- shared parse helpers ----------

def _none_or_str(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()
    return s or None


def _clean_tags(tags: Any, lower: dict[str, str]) -> list[str]:
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for t in tags:
        canon = lower.get(str(t).strip().lower())
        if canon and canon not in out:
            out.append(canon)
        if len(out) >= MAX_TAGS:
            break
    return out


def _str_list(items: Any, cap: int) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(x).strip() for x in items if str(x).strip()][:cap]
