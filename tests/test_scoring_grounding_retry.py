"""Regression test for a /code-review finding: `_score_batch_grounded`'s
retry call could raise `QuotaExhaustedError` uncaught, which discarded
the batch's ALREADY-grounded results (never returned, never saved) even
though they needed no further work.

Runs without pytest:
    .venv/bin/python tests/test_scoring_grounding_retry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.gemini import QuotaExhaustedError  # noqa: E402
from core.matching import semantic_score as ss  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


RESUME = "Experienced Python developer with SQL and AWS skills."

GOOD_SECTIONS = {
    "experience": {"score": 80, "matched": ["Python"], "gaps": [], "reasoning": "ok"},
    "skills": {"score": 80, "matched": ["SQL"], "gaps": [], "reasoning": "ok"},
    "role": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
    "domain": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
    "education": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
}

# job2's "skills.matched" claims Salesforce, which is NOT in RESUME — this
# fails the grounding check and triggers a retry.
BAD_SECTIONS = {
    "experience": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
    "skills": {"score": 80, "matched": ["Salesforce"], "gaps": [], "reasoning": "ok"},
    "role": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
    "domain": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
    "education": {"score": 80, "matched": [], "gaps": [], "reasoning": "ok"},
}

JOBS = [
    {"id": "job1", "title": "T1", "company": "C", "description": "d"},
    {"id": "job2", "title": "T2", "company": "C", "description": "d"},
]


class FakeClient:
    """Minimal duck-typed stand-in for GeminiClient. `responses` is a list
    consumed in order across successive `generate_json` calls; an
    Exception entry is raised instead of returned."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls = 0
        self.model_name = "fake-model"
        self.last_model_used = "fake-model"

    def generate_json(self, prompt: str) -> dict:
        r = self.responses[self.calls]
        self.calls += 1
        if isinstance(r, Exception):
            raise r
        return r

    def all_models_exhausted(self) -> bool:
        return False


def main() -> int:
    first_batch_response = {
        "scores": [
            {"job_id": "job1", "sections": GOOD_SECTIONS, "hard_requirements": [], "reasoning": "good"},
            {"job_id": "job2", "sections": BAD_SECTIONS, "hard_requirements": [], "reasoning": "bad"},
        ]
    }
    client = FakeClient([first_batch_response, QuotaExhaustedError("out of quota")])

    resume_norm, resume_stems = ss._resume_ground_index(RESUME)
    results = ss._score_batch_grounded(
        RESUME, JOBS, client,
        lang="en", persona="a professional candidate", resume_id=None,
        resume_norm=resume_norm, resume_stems=resume_stems,
    )

    ids = {r.job_id for r in results}
    _assert("job1" in ids,
            "job1 was grounded on the first call and required no retry — it must "
            "survive even though job2's retry blew the quota")
    _assert("job2" not in ids,
            "job2 failed grounding and its retry hit QuotaExhaustedError — it "
            "should be dropped, not crash the whole batch")
    _assert(client.calls == 2, "expected exactly 2 generate_json calls: initial batch + one retry")

    print("OK — quota exhaustion during a grounding retry no longer discards good results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
