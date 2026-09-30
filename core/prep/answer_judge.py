"""Interviewer judge for Get Ready answer cards (ADR-058, Phase 4) — offline.

Why: Eduardo found cards that sounded complete but didn't answer the question
("How do you approach managing budgets?" → a paragraph with no approach). We
had no check for that. This grades ONE card the way a sharp interviewer would:

  - answers_the_question: does it answer what was asked (a "how" gets a how)?
  - specificity 1–5: concrete method / tools / own actions / real numbers vs vague;
  - filler_phrases: phrases that sound complete but say nothing;
  - invented_facts: claims NOT supported by the résumé + the candidate's
    clarifications (the no-new-data rule);
  - one_liner: the interviewer's call.

Works on both card formats: the v2 prose answer and the v3 skeleton (frame is
flattened; hint slots become "[MISSING: …]" so an honest gap isn't graded as a
fabrication, but still costs specificity).

CAVEAT (self-judging, same as core/resume/recruiter_judge.py): Gemini also
writes the cards. Read the numbers with that discount; `scripts/eval_answer_cards.py
--export-dir` dumps the cards so an independent model can grade them blind.
temperature=0.0 so a re-judge reproduces.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from core.llm.gemini import GeminiClient, GeminiError, QuotaExhaustedError

from . import prompts as P
from .toolkit import split_hints


@dataclass
class CardVerdict:
    answers_the_question: bool
    specificity: int                                  # 1–5
    filler_phrases: list[str] = field(default_factory=list)
    invented_facts: list[str] = field(default_factory=list)
    one_liner: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def card_text(card: dict) -> str:
    """Flatten a stored toolkit question to the text an interviewer would hear:
    the v2 `answer` prose, or the v3 `frame` sections (hints → [MISSING: …])."""
    if card.get("answer"):
        return str(card["answer"]).strip()
    lines: list[str] = []
    for sec in card.get("frame") or []:
        pts = []
        for pt in sec.get("points") or []:
            pts.append("".join(v if k == "t" else f"[MISSING: {v}]" for k, v in split_hints(str(pt))))
        lines.append(f"{sec.get('section', '')}: " + " / ".join(pts))
    if card.get("point_to_land"):
        lines.append(f"point to land: {card['point_to_land']}")
    return "\n".join(lines)


def judge_card(
    question: str, card_answer: str, resume_text: str, clarifications: dict[str, str],
    client: GeminiClient,
) -> Optional[CardVerdict]:
    """Grade one card. None on refusal / quota / malformed output (the harness
    records a skipped cell, never a fake pass)."""
    if not question.strip() or not card_answer.strip() or client.all_models_exhausted():
        return None
    clar = "\n".join(f"- Q: {q}\n  A: {a}" for q, a in clarifications.items()) or "(none)"
    prompt = f"""You are a sharp, fair hiring manager. A candidate prepared this answer to your interview question. Judge the ANSWER, not the person.

{P.RULE_BLOCK}

Question you asked:
{question}

The candidate's prepared answer (bullets are fine; "[MISSING: …]" marks a gap the candidate still has to fill — do not count it as invented, but it lowers specificity):
{card_answer}

Evidence you may check claims against — the résumé and the candidate's own clarifications:
Résumé:
---
{P.clip(resume_text, P.MAX_RESUME_CHARS)}
---
Clarifications:
{clar}

Judge:
1. answers_the_question: true only if it answers what was ASKED. A "how do you…" question must get a method or steps; a "tell me about a time" must get a specific situation, the candidate's own actions and a result.
2. specificity: 1 = generic, could be anyone; 3 = some concrete details; 5 = concrete method, tools, own actions and real outcomes throughout.
3. filler_phrases: exact phrases that sound complete but say nothing (e.g. "strict oversight", "effectively", "rigorous tracking"). Empty list if none.
4. invented_facts: claims not supported by the résumé or the clarifications (a number, employer, tool or result that isn't there, or numbers combined into a new claim). Empty list if none.
5. one_liner: your one-sentence call as the interviewer.

Return JSON only:
{{ "answers_the_question": true, "specificity": 3, "filler_phrases": ["string"], "invented_facts": ["string"], "one_liner": "string" }}"""
    try:
        raw = client.generate_json(prompt, temperature=0.0)
    except (GeminiError, QuotaExhaustedError):
        return None
    return _parse(raw, client.last_model_used or client.model_name or "")


def _parse(raw: Any, model: str) -> Optional[CardVerdict]:
    if not isinstance(raw, dict) or "answers_the_question" not in raw:
        return None
    ans = raw.get("answers_the_question")
    ans = ans if isinstance(ans, bool) else str(ans).strip().lower() in ("true", "yes", "1")
    try:
        spec = max(1, min(5, int(raw.get("specificity", 1))))
    except (TypeError, ValueError):
        spec = 1

    def _lst(k: str) -> list[str]:
        v = raw.get(k)
        return [str(x).strip() for x in v if str(x).strip()][:6] if isinstance(v, list) else []

    return CardVerdict(
        answers_the_question=ans, specificity=spec,
        filler_phrases=_lst("filler_phrases"), invented_facts=_lst("invented_facts"),
        one_liner=re.sub(r"\s+", " ", str(raw.get("one_liner", "")).strip()), model=model,
    )
