"""Readiness (D9, REQ-041) — the ONE per-interview readiness definition, used
everywhere (Home hero, interview rows). A band, NOT a percentage (design brief
§3/§4) — the number is only the progress-bar fill, never shown as "82% ready".

The four levels and their rules (D9):
  - not_started : brief not reviewed
  - getting_there : brief reviewed + stories mapped to at least half the competencies
  - almost_ready : every competency has a story + at least 1 practice session
  - ready : every competency answered at "Solid" or better in practice

Computed in CODE from cached artifacts (brief P1 + mapping P3) + practice signals
(done-session count + the latest P9 debrief's competency bands), never asked of
the model. Always paired with a "what's missing" line (D9: more useful than a
number).
"""
from __future__ import annotations

import math
from typing import Optional

from core import db

from . import brief as p1
from . import mapping as p3

LEVELS = ("not_started", "getting_there", "almost_ready", "ready")

# Progress-bar fill only — NOT a score shown to the user (design brief §3).
_PCT = {"not_started": 12, "getting_there": 45, "almost_ready": 78, "ready": 100}


def compute(interview: dict, *, lang: Optional[str] = None, path=db.DB_PATH) -> dict:
    """Return {level, pct, missing, missing_count} for one interview. `missing`
    is an i18n key suffix (prep2.ready.missing.<missing>); `missing_count` fills
    its {n} placeholder where relevant (0 otherwise)."""
    iid = interview.get("id")
    resume_hash = interview.get("resume_hash", "")

    brief = p1.read_cached_brief(iid, lang=lang, path=path) if iid else None
    if brief is None or not brief.competencies:
        return _result("not_started", "review_brief", 0)

    n = len(brief.competencies)
    comp_ids = [c.id for c in brief.competencies]
    stories = db.list_stories(resume_hash, status="saved", path=path)
    mapping = p3.read_cached_mapping(iid, stories, lang=lang, path=path) or []
    mapped = sum(1 for m in mapping if m.story_id)
    half = math.ceil(n / 2)

    # Brief built but stories under-mapped — still the lowest band; the missing
    # line carries the nuance (add stories vs map them).
    if mapped < half:
        if not stories:
            return _result("not_started", "add_stories", 0)
        return _result("not_started", "map_stories", max(half - mapped, 1))

    practiced = db.count_practice_sessions(iid, path=path)

    # getting_there: half mapped, but not (fully mapped AND practised once).
    if not (mapped >= n and practiced >= 1):
        if mapped < n:
            return _result("getting_there", "unmapped_competencies", n - mapped)
        return _result("getting_there", "do_practice", 0)

    # almost_ready → ready: ready needs every competency at solid+ in the latest
    # debrief; otherwise there are weak spots to strengthen.
    bands = _latest_competency_bands(iid, path=path)
    weak = [cid for cid in comp_ids if bands.get(cid, "needs_work") == "needs_work"]
    if weak:
        return _result("almost_ready", "strengthen", len(weak))
    return _result("ready", "ready", 0)


def _latest_competency_bands(interview_id: int, *, path=db.DB_PATH) -> dict:
    """competency_id → band from the most recent DONE session's P9 debrief.
    Empty when no debrief yet (→ everything reads as needs_work, correctly)."""
    for s in db.list_practice_sessions(interview_id, path=path):
        if s.get("status") == "done" and isinstance(s.get("debrief"), dict):
            out = {}
            for b in (s["debrief"].get("competency_bands") or []):
                if isinstance(b, dict) and b.get("competency_id"):
                    out[str(b["competency_id"])] = str(b.get("band", "needs_work"))
            return out
    return {}


def _result(level: str, missing: str, missing_count: int) -> dict:
    return {"level": level, "pct": _PCT[level],
            "missing": missing, "missing_count": missing_count}
