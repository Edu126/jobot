"""Prep orchestrator (ADR-048 → ADR-057, REQ-041) — two calls per interview.

  1. **P1 Brief** — the user waits on it on the generating screen (Flow A3). It
     also writes the *fact questions*: specifics the résumé doesn't state that
     this interview will probe.
  2. **The toolkit** (`toolkit.py`) — ONE call with the full context (brief +
     the candidate's answers to those fact questions + Story Bank + résumé)
     writes the likely questions with MY answers, the story per competency (or a
     STAR draft) and the questions to ask. It starts when the candidate leaves
     the Brief (answers submitted or skipped), so it can use the answers.

Was P2 ∥ P3 → P4 (three calls re-sending the same context, each seeing a slice).
Eduardo (2026-09-29): build it once, from the brief — no layered "Building this
part…". The blocking Gemini calls run in threads (`asyncio.to_thread`). Each
stage gets its OWN GeminiClient from `make_client` (per-call mutable state).
A failed call degrades to None; it never raises out of here. Status advances
created → brief_ready → toolkit_ready.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from core import db
from core.llm.gemini import GeminiClient

from . import brief as p1
from . import toolkit as tk

MakeClient = Callable[[], GeminiClient]


@dataclass
class ToolkitResult:
    brief: Optional[p1.Brief] = None
    toolkit: Optional[tk.Toolkit] = None

    @property
    def brief_ready(self) -> bool:
        return self.brief is not None and not self.brief.is_empty()


async def build_toolkit(
    interview: dict,
    resume_text: str,
    *,
    make_client: MakeClient,
    stories: Optional[list[dict]] = None,
    research: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    update_status: bool = True,
    path=db.DB_PATH,
) -> ToolkitResult:
    """Full build: P1, then the toolkit call. Returns whatever succeeded. If P1
    yields no usable brief, the toolkit is skipped (nothing to hang it on)."""
    brief = await build_brief(
        interview, resume_text, make_client=make_client, research=research,
        lang=lang, use_cache=use_cache, update_status=update_status, path=path)
    if brief is None:
        return ToolkitResult(brief=None)
    toolkit = await run_toolkit(
        interview, brief, resume_text, make_client=make_client, stories=stories,
        lang=lang, use_cache=use_cache, update_status=update_status, path=path)
    return ToolkitResult(brief=brief, toolkit=toolkit)


async def build_brief(
    interview: dict,
    resume_text: str,
    *,
    make_client: MakeClient,
    research: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    update_status: bool = True,
    path=db.DB_PATH,
) -> Optional[p1.Brief]:
    """Just P1 — the step the generating screen waits on. Advances status to
    brief_ready on success."""
    brief = await asyncio.to_thread(
        p1.get_or_generate_brief, interview, resume_text, make_client(),
        research=research or [], lang=lang, use_cache=use_cache, path=path)
    if brief is None or brief.is_empty():
        return None
    if update_status and interview.get("id"):
        db.update_interview_status(interview["id"], "brief_ready", path=path)
    return brief


async def run_toolkit(
    interview: dict,
    brief: p1.Brief,
    resume_text: str,
    *,
    make_client: MakeClient,
    stories: Optional[list[dict]] = None,
    lang: Optional[str] = None,
    use_cache: bool = True,
    update_status: bool = True,
    path=db.DB_PATH,
) -> Optional[tk.Toolkit]:
    """The single toolkit call off an already-built brief (a cache hit after the
    first build). None on failure — never raises."""
    try:
        result = await asyncio.to_thread(
            tk.get_or_generate_toolkit, interview, brief.to_dict_for_cache(),
            stories or [], resume_text, make_client(),
            lang=lang, use_cache=use_cache, path=path)
    except Exception:  # noqa: BLE001 — degrade to None, like every stage
        return None
    if result is not None and update_status and interview.get("id"):
        db.update_interview_status(interview["id"], "toolkit_ready", path=path)
    return result
