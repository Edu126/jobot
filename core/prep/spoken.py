"""P10 — the spoken version of a prepared answer (REQ-051, ADR-078).

The live interview aid used to glue the answer frame's points together, which
read like a list ("I work as… I led… I want…"). This rewrites ONE frame into a
short first-person script with spoken connectors (first / before that / so /
what draws me…), for glancing at while you talk. It may add connectors only:
every fact and number stays exactly as in the frame (GOV-005).

Cached per (interview, question id, lang, PROMPT_VERSION + frame hash) in
prep_artifacts, so a regenerated toolkit (new frame) gets a new script and
everything else is a free cache hit."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Callable, Optional

from core import db
from core.llm.gemini import GeminiClient, GeminiError
from core.prep.toolkit import split_hints
from core.settings import language_instruction, resolve_output_language

PROMPT_VERSION = "2026-10-12-spoken-v2-true-connectors"
_KIND = "spoken:"


def _plain(text: str) -> str:
    """A point without its [[hint: …]] slots (ADR-058) — a gap the candidate
    hasn't filled is left out of the script, never guessed."""
    return " ".join("".join(v for k, v in split_hints(str(text)) if k != "h").split())


def _frame_text(frame: list, point: str) -> str:
    lines = [f"- {_plain(pt)}" for sec in frame or [] if isinstance(sec, dict)
             for pt in (sec.get("points") or []) if _plain(pt)]
    if point:
        lines.append(f"- Point to land: {point}")
    return "\n".join(lines)


def build_prompt(question: str, frame: list, point: str, *, lang: Optional[str] = None) -> str:
    return f"""You turn a candidate's prepared interview answer into what they would actually SAY out loud.

Question they were asked: {question}

Their prepared answer, as notes:
{_frame_text(frame, point)}

Write it as a short spoken script in the first person, the way a calm, confident person answers in a real interview:
- Make it flow as one conversation, not a list: merge short notes into one sentence, use contractions ("I'm", "we'd"), and connect ideas with spoken connectors that match what the notes say:
  - steps of what you did → "First…", "Then…", "From there…", "That's when…"
  - a result → "As a result…", "In the end…"
  - time ("Right now…", "Before that…", "Currently") ONLY when the notes themselves say when — never invent an order of events.
  - Never start two sentences with the same connector; use "So" at most once.
- You may add connectors and light framing words ONLY. Every fact, name, number and claim must come from the notes, exactly as written. Never add a fact, a number, a duration, a feeling or a result that isn't in the notes. Never change a number.
- Close with their key message (the point to land), said naturally ("So, in short, …").
- 60–120 words. Plain sentences someone can read at a glance while speaking. No headings, no bullets, no quotes around it.

{language_instruction(lang)}

Return JSON only: {{"script": "string"}}"""


def _cache_version(frame: list, point: str) -> str:
    h = hashlib.sha1(json.dumps([frame, point], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]
    return f"{PROMPT_VERSION}:{h}"


def spoken_script(
    interview_id: int, question: dict, *, lang: Optional[str] = None,
    client: Optional[GeminiClient] = None,
) -> Optional[str]:
    """The cached script for one question, generating it on a miss when a
    client is given. None when the question has no frame or the call fails —
    the aid then falls back to the frame's points."""
    frame = question.get("frame") or []
    point = str(question.get("point_to_land") or "")
    if not frame:
        return None
    lang = resolve_output_language(lang)
    kind, version = _KIND + str(question.get("id")), _cache_version(frame, point)
    hit = db.get_prep_artifact(interview_id, kind, lang, version)
    if hit and isinstance(hit["artifact"], dict) and hit["artifact"].get("script"):
        return hit["artifact"]["script"]
    if client is None:
        return None
    try:
        raw = client.generate_json(build_prompt(str(question.get("text", "")), frame, point, lang=lang),
                                   temperature=0.0)
    except GeminiError as e:
        print(f"[spoken] script failed for {kind}: {e}")
        return None
    script = str((raw or {}).get("script") or "").strip()
    if not script:
        return None
    db.save_prep_artifact(interview_id, kind, lang, version, {"script": script},
                          model=getattr(client, "last_model_used", "") or "")
    return script


async def attach_scripts(
    interview_id: int, questions: list[dict], *, lang: Optional[str],
    make_client: Callable[[], GeminiClient],
) -> None:
    """Fill `q["spoken"]` on every question with a frame, in parallel (one
    client per call so `last_model_used` doesn't clobber). Cache hits cost
    nothing; failures leave the question without a script."""
    async def one(q: dict) -> None:
        s = await asyncio.to_thread(spoken_script, interview_id, q, lang=lang, client=make_client())
        if s:
            q["spoken"] = s
    await asyncio.gather(*(one(q) for q in questions if q.get("frame")))
