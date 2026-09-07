"""Prep kit generation + parsing (REQ-023 / ADR-028). Locks down:
  1. _parse_qa keeps a grounded STAR and grounded talking-points, and DROPS
     any item with no usable answer, a bad kind, or no question
     (grounded-or-none — never render an unanswerable question);
  2. _parse_reverse keeps questions, defaults a missing category;
  3. _defense_seeds reuses REQ-018: a job-bound session pulls its REAL gaps +
     defense hooks (and only the real ones);
  4. get_or_generate_kit generates + caches on a miss, and a second call is a
     cache hit (no re-generation);
  5. an empty generated kit → None.

No network: a fake GeminiClient supplies the JSON; persona_line is stubbed.
    .venv/bin/python tests/test_prep_kit.py
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.matching import gap_enhance  # noqa: E402
from core.prep import kit as K  # noqa: E402
from core.resume import ai_summary  # noqa: E402

ai_summary.persona_line = lambda *a, **k: "a mid-career data analyst"  # type: ignore


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


_KIT = {
    "star_qa": [
        {"kind": "behavioral", "question": "Tell me about a data process you automated.",
         "star": {"situation": "ATIP backlog", "task": "cut turnaround",
                  "action": "built a Python/SQL pipeline", "result": "saved 200+ hours"}},
        {"kind": "why_you", "question": "Why you?",
         "talking_points": ["10y in public-sector data", "governance-first mindset"]},
        # dropped: no usable answer (grounded-or-none)
        {"kind": "situational", "question": "A question we can't ground.", "star": {}},
        # dropped: bad kind
        {"kind": "trivia", "question": "x", "talking_points": ["y"]},
    ],
    "reverse_qs": [
        {"category": "Culture & Team", "question": "How do you balance speed vs governance?"},
        {"question": "What does success look like in 90 days?"},  # category defaults
    ],
}


def _fresh() -> Path:
    return _mk(tempfile.mkdtemp())


def _mk(tmp) -> Path:
    p = Path(tmp) / "kit.sqlite"
    db.init_db(p)
    return p


def _seed_session(p: Path, *, job_id=None) -> int:
    con = sqlite3.connect(p)
    con.execute("PRAGMA foreign_keys = ON")
    if job_id:
        con.execute("INSERT INTO jobs(id,title,company,first_seen,last_seen) "
                    "VALUES (?,?,?,'now','now')", (job_id, "Senior BA", "CMHC"))
    con.execute(
        "INSERT INTO prep_sessions(id,resume_hash,job_id,company,role_title,jd_text,lang,source,created_at) "
        "VALUES (1,'cand1',?, 'CMHC','Senior BA','Analyze housing data.','en','from_job','now')",
        (job_id,))
    con.commit()
    con.close()
    return 1


# ---- pure parsers ----

def test_parse_qa_grounded_or_none():
    out = K._parse_qa(_KIT["star_qa"])
    kinds = [q.kind for q in out]
    _assert(kinds == ["behavioral", "why_you"], f"only grounded/valid items kept, got {kinds}")
    _assert(out[0].star and out[0].star["result"].startswith("saved"), "STAR preserved")
    _assert(out[1].talking_points and len(out[1].talking_points) == 2, "talking points preserved")
    print("PASS test_parse_qa_grounded_or_none")


def test_parse_reverse_defaults_category():
    out = K._parse_reverse(_KIT["reverse_qs"])
    _assert(len(out) == 2, "both reverse questions kept")
    _assert(out[0].category == "Culture & Team", "explicit category kept")
    _assert(out[1].category == "General", "missing category defaults to General")
    print("PASS test_parse_reverse_defaults_category")


def test_parse_garbage_is_safe():
    for bad in (None, "nope", [42, None, {}], [{"kind": "behavioral"}]):
        _assert(K._parse_qa(bad) == [], f"garbage QA → empty for {bad!r}")
    _assert(K._parse_reverse(None) == [], "garbage reverse → empty")
    print("PASS test_parse_garbage_is_safe")


# ---- defense-hook reuse ----

def test_defense_seeds_reuses_real_gaps():
    p = _fresh()
    # a résumé so save_gap_enhancement can resolve resume_id → text_hash
    con = sqlite3.connect(p)
    con.execute("INSERT INTO resumes(id,filename,uploaded_at,parsed_json,is_current,text_hash) "
                "VALUES (7,'cv.pdf','now','{}',1,'cand1')")
    con.commit(); con.close()
    db.save_gap_enhancement(
        "job-9", 7, "en", gap_enhance.PROMPT_VERSION,
        [{"gap": "Enterprise Architecture", "kind": "real", "suggestion": "Lead with your data-platform work."},
         {"gap": "AutoCAD", "kind": "wording", "suggestion": "Name Autodesk explicitly."}],
        "m", path=p)
    seeds = K._defense_seeds({"job_id": "job-9"}, 7, "en", p)
    _assert(len(seeds) == 1, f"only REAL gaps seed defense, got {seeds}")
    _assert(seeds[0]["gap"] == "Enterprise Architecture" and seeds[0]["defense_hook"].startswith("Lead"),
            "real gap + its defense hook carried through")
    # unbound session → no seeds
    _assert(K._defense_seeds({"job_id": None}, 7, "en", p) == [], "unbound session seeds nothing")
    print("PASS test_defense_seeds_reuses_real_gaps")


# ---- end to end ----

def test_generate_then_cache():
    p = _fresh()
    sid = _seed_session(p, job_id=None)
    client = _FakeClient(payload=_KIT)
    session = {"id": sid, "company": "CMHC", "role_title": "Senior BA",
               "jd_text": "Analyze housing data.", "job_id": None}
    out = K.get_or_generate_kit(session, 7, "my real résumé text", client, lang="en", path=p)
    _assert(out is not None and not out.is_empty(), "miss should generate a kit")
    _assert([q.kind for q in out.star_qa] == ["behavioral", "why_you"], "parsed kit cached")
    _assert(len(out.reverse_qs) == 2, "reverse questions present")
    _assert(out.created_at, "created_at from stored row")
    # second call → cache hit, no re-generation
    out2 = K.get_or_generate_kit(session, 7, "my real résumé text", client, lang="en", path=p)
    _assert(out2 is not None and client.calls == 1, "cache hit must not re-generate")
    print("PASS test_generate_then_cache")


def test_empty_kit_returns_none():
    p = _fresh()
    _seed_session(p, job_id=None)
    client = _FakeClient(payload={"star_qa": [], "reverse_qs": []})
    session = {"id": 1, "company": "CMHC", "role_title": "BA", "jd_text": "", "job_id": None}
    out = K.get_or_generate_kit(session, 7, "résumé", client, lang="en", path=p)
    _assert(out is None, "empty kit → None (render nothing)")
    print("PASS test_empty_kit_returns_none")


if __name__ == "__main__":
    test_parse_qa_grounded_or_none()
    test_parse_reverse_defaults_category()
    test_parse_garbage_is_safe()
    test_defense_seeds_reuses_real_gaps()
    test_generate_then_cache()
    test_empty_kit_returns_none()
    print("all prep-kit tests passed")
