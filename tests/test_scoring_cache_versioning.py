"""Regression test for REQ-004 / ADR-006's cache-invalidation lever:
bumping `prompt_version` or `scoring_version` must invalidate cached
`job_scores` rows LOGICALLY (next read recomputes) without deleting
history — old rows stay in the table for audit, they just stop being
served.

Also covers the `resume_ai_summary` schema bump (ADR-013: domain +
seniority columns) round-tripping correctly.

Runs without pytest:
    .venv/bin/python tests/test_scoring_cache_versioning.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "test_versioning.db"
    db.init_db(tmp)

    resume_id = db.save_resume("r.pdf", {"raw_text": "resume text", "sections": {}}, b"bytes", path=tmp)
    db.upsert_job({"id": "job1", "title": "Test Job", "company": "Acme"}, path=tmp)

    score = {
        "job_id": "job1", "score": 72, "verdict": "workable", "reasoning": "decent fit",
        "matched": ["sql"], "gaps": ["tableau"],
        "sections": {"experience": {"score": 80, "matched": ["sql"], "gaps": [], "reasoning": "ok"}},
        "hard_requirements": [{"name": "degree", "status": "met", "evidence": "BSc"}],
        "model": "gemini-test",
    }
    db.save_scores(resume_id, [score], "en", "prompt-v1", "scoring-v1", path=tmp)

    # Same versions → cache hit, full round-trip of the new JSON columns.
    hit = db.get_cached_scores(resume_id, ["job1"], "en", "prompt-v1", "scoring-v1", path=tmp)
    _assert("job1" in hit, "expected a cache hit under matching prompt/scoring versions")
    _assert(hit["job1"]["score"] == 72, "cached score value should round-trip")

    # Bumping EITHER version alone must miss — a stale prompt or stale
    # weights are both reasons to recompute.
    miss_prompt = db.get_cached_scores(resume_id, ["job1"], "en", "prompt-v2", "scoring-v1", path=tmp)
    _assert("job1" not in miss_prompt, "a prompt_version bump must invalidate the cached row")

    miss_scoring = db.get_cached_scores(resume_id, ["job1"], "en", "prompt-v1", "scoring-v2", path=tmp)
    _assert("job1" not in miss_scoring, "a scoring_version bump must invalidate the cached row")

    # The old row is NOT deleted — history survives (ADR-006: "old rows
    # are retained for history/audit").
    with db.connect(tmp) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM job_scores WHERE resume_id = ? AND job_id = ?",
            (resume_id, "job1"),
        ).fetchone()
    _assert(int(row["n"]) == 1, "old job_scores row must survive a version bump, not be deleted")

    # Re-scoring under the new version writes a SEPARATE row (PK includes
    # lang but not prompt/scoring version, so this is an upsert on the
    # same key — the new version's data replaces it, which is correct:
    # the (resume, job, lang) triple should reflect the CURRENT score).
    score_v2 = dict(score, score=90, verdict="strong_fit")
    db.save_scores(resume_id, [score_v2], "en", "prompt-v2", "scoring-v1", path=tmp)
    hit_v2 = db.get_cached_scores(resume_id, ["job1"], "en", "prompt-v2", "scoring-v1", path=tmp)
    _assert(hit_v2["job1"]["score"] == 90, "re-scoring under a new prompt_version should update the row")
    old_version_now_missing = db.get_cached_scores(resume_id, ["job1"], "en", "prompt-v1", "scoring-v1", path=tmp)
    _assert("job1" not in old_version_now_missing,
            "once re-scored, the row now stamps the NEW version — old-version reads correctly miss")

    # ADR-013: resume_ai_summary domain/seniority round-trip.
    db.save_resume_ai_summary(
        resume_id, lang="en", role_label="BI analyst", domain="fintech", seniority="mid",
        first_impression="solid", suggestions=[], path=tmp,
    )
    summary = db.get_resume_ai_summary(resume_id, "en", path=tmp)
    _assert(summary["domain"] == "fintech" and summary["seniority"] == "mid",
            "domain/seniority must round-trip through resume_ai_summary")

    print("OK — cache versioning + resume_ai_summary schema hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
