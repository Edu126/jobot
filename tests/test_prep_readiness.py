"""Readiness D9 (REQ-041) — the one per-interview readiness definition. Locks:
  1. no brief → not_started / review_brief;
  2. brief but no stories in the bank → not_started / add_stories;
  3. brief + stories but under-half mapped → not_started / map_stories (count);
  4. >= half competencies mapped → getting_there / unmapped_competencies (count);
  5. every competency mapped → getting_there / do_practice (ceiling until Practice
     exists — almost_ready/ready need practice sessions, ADR-049).
    .venv/bin/python tests/test_prep_readiness.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.prep import brief as B  # noqa: E402
from core.prep import toolkit as T  # noqa: E402
from core.prep import readiness as R  # noqa: E402


def _assert(c, m):
    if not c:
        raise AssertionError(m)


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "ready.sqlite"
    db.init_db(p)
    return p


def _seed_brief(p, iid, n):
    comps = [B.Competency(f"c{i+1}", f"Comp{i+1}", "x", "solid") for i in range(n)]
    db.save_prep_artifact(iid, "brief", "en", B.PROMPT_VERSION,
                          B.Brief(competencies=comps).to_dict_for_cache(), "f", path=p)


def _seed_mapping(p, iid, cand, covered_ids):
    """Story picks now live in the one toolkit artifact (ADR-057)."""
    stories = db.list_stories(cand, status="saved", path=p)
    brief = B.read_cached_brief(iid, lang="en", path=p).to_dict_for_cache()
    version = T._cache_version(brief, stories, T.read_facts(iid, path=p))
    sid = str(stories[0]["id"]) if stories else "1"
    rows = [{"competency_id": cid, "story_id": sid} for cid in covered_ids]
    db.save_prep_artifact(iid, "toolkit", "en", version,
                          {"questions": [], "stories": rows, "questions_to_ask": []}, "f", path=p)


def test_readiness_levels():
    p = _fresh()
    iid = db.create_interview("cand1", "Acme", "DA", "jd", "en", "paste_text", path=p)
    iv = db.get_interview(iid, path=p)

    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "not_started" and r["missing"] == "review_brief", f"no brief, got {r}")

    _seed_brief(p, iid, 2)
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "not_started" and r["missing"] == "add_stories", f"no stories, got {r}")

    db.create_story("cand1", title="S1", action="I led", result="won 20%", path=p)
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "not_started" and r["missing"] == "map_stories", f"unmapped, got {r}")

    _seed_mapping(p, iid, "cand1", ["c1"])  # 1 of 2 = half
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "getting_there" and r["missing"] == "unmapped_competencies"
            and r["missing_count"] == 1, f"half mapped, got {r}")

    _seed_mapping(p, iid, "cand1", ["c1", "c2"])  # full
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "getting_there" and r["missing"] == "do_practice",
            f"full mapped, no practice → getting_there/do_practice, got {r}")

    # a done session with a weak competency → almost_ready / strengthen
    s1 = db.create_practice_session(iid, path=p)
    db.save_practice_debrief(s1, {"competency_bands": [
        {"competency_id": "c1", "band": "solid"}, {"competency_id": "c2", "band": "needs_work"}]}, path=p)
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "almost_ready" and r["missing"] == "strengthen" and r["missing_count"] == 1,
            f"weak competency → almost_ready/strengthen, got {r}")

    # a newer done session, all solid+ → ready
    s2 = db.create_practice_session(iid, path=p)
    db.save_practice_debrief(s2, {"competency_bands": [
        {"competency_id": "c1", "band": "strong"}, {"competency_id": "c2", "band": "solid"}]}, path=p)
    r = R.compute(iv, lang="en", path=p)
    _assert(r["level"] == "ready", f"all solid+ → ready, got {r}")
    print("PASS test_readiness_levels")


if __name__ == "__main__":
    test_readiness_levels()
    print("all readiness tests passed")
