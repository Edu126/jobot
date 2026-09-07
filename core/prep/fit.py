"""Prep-stage fit brief (REQ-025). At the PREP stage the candidate already has
the interview, so we DON'T show a bare score % (demoralizing, and beside the
point — they were invited). Instead we surface a **qualitative band** + the
scorer's narrative + strengths to lean into + gaps to be ready for. Honest
(gaps are shown) but esteem-protective (no harsh number, strengths first).

The brief comes from the one-shot import score (stored on the session as
`match_brief` JSON, ADR-030) or, for a bound session, is derived from the cached
`job_scores` row.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from core import db

# Band thresholds — deliberately kind at the bottom: a low score reads as a
# "stretch" (they were invited anyway), never a failing grade.
_STRONG = 75
_SOLID = 50

# Hard caps so the context bar can NEVER bloat (REQ-025): at most 3 strengths /
# 3 gaps, each a short phrase, and a one-line narrative. The UI also clamps as a
# backstop, but the contract layer is the real guarantee.
MAX_ITEMS = 3
MAX_ITEM_CHARS = 80
MAX_REASONING_CHARS = 220


def band_from_score(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    if score >= _STRONG:
        return "strong"
    if score >= _SOLID:
        return "solid"
    return "stretch"


def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _coerce_list(value: Any, n: int = MAX_ITEMS) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [_clip(str(x), MAX_ITEM_CHARS) for x in value if str(x).strip()][:n]


def sanitize_brief(d: Any) -> dict:
    """The ONE place the fit-brief size contract lives (REQ-025): clip the
    narrative and cap/clip the strength & gap lists. Every writer (the import
    scorer, the confirm round-trip) and the reader go through this, so the caps
    can never diverge across layers. A non-dict input (e.g. a stored `"null"`
    that json.loads to None) degrades to an empty brief, never raises."""
    if not isinstance(d, dict):
        d = {}
    return {
        "reasoning": _clip(str(d.get("reasoning") or ""), MAX_REASONING_CHARS),
        "matched": _coerce_list(d.get("matched")),
        "gaps": _coerce_list(d.get("gaps")),
    }


def brief_for_session(session: dict, path=db.DB_PATH) -> Optional[dict]:
    """{score, band, reasoning, matched[], gaps[]} for the context bar, or None
    when we have no fit read at all."""
    score = session.get("match_score")
    reasoning, matched, gaps = "", [], []

    raw = session.get("match_brief")
    if raw:
        try:
            b = sanitize_brief(json.loads(raw))
            reasoning, matched, gaps = b["reasoning"], b["matched"], b["gaps"]
        except (TypeError, ValueError):
            pass
    elif session.get("job_id"):
        row = db.get_bound_fit(session["resume_hash"], session["job_id"], path=path)
        if row:
            if score is None:
                score = row.get("score")
            b = sanitize_brief(row)
            reasoning, matched, gaps = b["reasoning"], b["matched"], b["gaps"]

    if score is None and not reasoning and not matched and not gaps:
        return None
    return {"score": score, "band": band_from_score(score),
            "reasoning": reasoning, "matched": matched, "gaps": gaps}
