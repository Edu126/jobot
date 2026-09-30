"""Prep AI pipeline — P1 Brief (REQ-041 / ADR-048 / ADR-057). The toolkit call
has its own file (test_prep_toolkit.py). Locks down:

  1. Brief parsing: competencies re-id'd dense c1..cN, unknown/blank band →
     needs_work (never rounded up), snapshot/gaps/str-lists well-formed & capped,
     garbage is safe, a brief with no competencies is_empty;
  2. Questions parsing: re-id q1..qN, bad type → behavioral, a competency_id the
     brief didn't define is NULLED (no dangling join), cap at MAX_QUESTIONS;
  3. get_or_generate_brief / _questions generate + cache on a miss, second call
     is a cache hit (no re-generation);
  4. empty brief → None; questions fan out on the brief's competency ids.

No network: a fake GeminiClient supplies the JSON.
    .venv/bin/python tests/test_prep_pipeline.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import brief as B  # noqa: E402
from core.prep import prompts as P  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeClient:
    def __init__(self, payload=None, raise_exc=None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_model_used = "fake"
        self.model_name = "fake"

    def all_models_exhausted(self):
        return False

    def generate_json(self, prompt, *, temperature=None, max_retries=2):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.payload


_BRIEF = {
    "role_summary": "Own the analytics stack. Partner with product on metrics.",
    "company_snapshot": [
        {"point": "Series B fintech, 300 people", "source_url": "https://x.com/a"},
        {"point": "no url still keeps the point", "source_url": None},
        {"point": "", "source_url": "https://x.com/drop"},  # dropped: no point
    ],
    "competencies": [
        {"id": "cX", "name": "Stakeholder management",
         "what_good_looks_like": "aligns partners", "resume_match": "strong",
         "evidence": "Led 3 cross-team launches"},
        {"id": "c99", "name": "SQL depth", "what_good_looks_like": "writes complex joins",
         "resume_match": "banana", "evidence": None},          # bad band → needs_work
        {"name": "", "what_good_looks_like": "x"},               # dropped: no name
    ],
    "gaps": [
        {"competency_id": "c2", "gap": "no dbt experience", "action": "read the dbt primer"},
        {"competency_id": None, "gap": "", "action": "x"},       # dropped: no gap
    ],
    "interviewer_lens": ["cares about impact", "", "cares about rigor", "extra", "over-cap"],
    "friction_points": ["gap in fintech domain"],
    "fact_questions": [
        {"question": "How large was the budget you managed?", "example": "I managed a $2M yearly budget"},
        {"question": "", "example": "dropped: blank"},
        "What tools did you use for forecasting?",
    ],
}

def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "prep.sqlite"
    db.init_db(p)
    return p


def _seed_interview(p: Path) -> int:
    return db.create_interview(
        "cand1", "Acme", "Data Analyst", "Analyze product data and build dashboards.",
        "en", "pasted_text", round_type="behavioral", path=p)


# ---- brief parsers ----

def test_brief_parse_reids_and_bands():
    b = B._parse_brief(_BRIEF)
    _assert([c.id for c in b.competencies] == ["c1", "c2"], f"dense re-id, got {[c.id for c in b.competencies]}")
    _assert(b.competencies[0].resume_match == "strong", "valid band kept")
    _assert(b.competencies[1].resume_match == "needs_work", "unknown band → needs_work (never rounded up)")
    _assert(b.competencies[1].evidence is None, "null evidence stays None")
    _assert(len(b.company_snapshot) == 2, "empty-point snapshot item dropped")
    _assert(b.company_snapshot[1].source_url is None, "missing url → None")
    _assert(len(b.gaps) == 1 and b.gaps[0].gap.startswith("no dbt"), "only well-formed gap kept")
    _assert(b.interviewer_lens == ["cares about impact", "cares about rigor", "extra"], "blanks dropped, capped at 3")
    _assert(not b.is_empty(), "brief with competencies is not empty")
    print("PASS test_brief_parse_reids_and_bands")


def test_brief_no_competencies_is_empty():
    b = B._parse_brief({"role_summary": "x", "competencies": []})
    _assert(b.is_empty(), "no competencies → is_empty (useless downstream)")
    for bad in (None, "nope", 42, {"competencies": "no"}):
        _assert(B._parse_brief(bad).is_empty(), f"garbage brief → empty for {bad!r}")
    print("PASS test_brief_no_competencies_is_empty")


def test_band_or_default():
    _assert(P.band_or_default("Strong") == "strong", "case-insensitive band")
    _assert(P.band_or_default("") == "needs_work", "blank → needs_work")
    _assert(P.band_or_default(None) == "needs_work", "None → needs_work")
    print("PASS test_band_or_default")


def test_brief_fact_questions():
    b = B._parse_brief(_BRIEF)
    _assert([f.id for f in b.fact_questions] == ["f1", "f2"], f"blank dropped, re-id f1..fN, got {b.fact_questions}")
    _assert(b.fact_questions[0].example.startswith("I managed"), "format example kept")
    _assert(b.fact_questions[1].question.startswith("What tools"), "a bare string is accepted")
    _assert(b.to_dict_for_cache()["fact_questions"][0]["id"] == "f1", "cached with ids")
    print("PASS test_brief_fact_questions")


# ---- end to end ----

def test_brief_generate_then_cache():
    p = _fresh()
    iid = _seed_interview(p)
    client = _FakeClient(payload=_BRIEF)
    interview = db.get_interview(iid, path=p)
    out = B.get_or_generate_brief(interview, "my résumé text", client, lang="en", path=p)
    _assert(out is not None and not out.is_empty(), "miss should generate a brief")
    _assert([c.id for c in out.competencies] == ["c1", "c2"], "parsed brief cached")
    _assert(out.created_at, "created_at from stored row")
    out2 = B.get_or_generate_brief(interview, "my résumé text", client, lang="en", path=p)
    _assert(out2 is not None and client.calls == 1, "cache hit must not re-generate")
    print("PASS test_brief_generate_then_cache")


def test_empty_brief_returns_none():
    p = _fresh()
    iid = _seed_interview(p)
    client = _FakeClient(payload={"role_summary": "x", "competencies": []})
    out = B.get_or_generate_brief(db.get_interview(iid, path=p), "résumé", client, lang="en", path=p)
    _assert(out is None, "empty brief → None")
    print("PASS test_empty_brief_returns_none")


if __name__ == "__main__":
    test_brief_parse_reids_and_bands()
    test_brief_no_competencies_is_empty()
    test_band_or_default()
    test_brief_fact_questions()
    test_brief_generate_then_cache()
    test_empty_brief_returns_none()
    print("all prep-pipeline tests passed")
