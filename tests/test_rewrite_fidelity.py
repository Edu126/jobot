"""Guardrail test: a tailoring pass must never silently drop whole experience
or education entries.

The bug this locks down (verified live on a real user's resume against the Fly
deploy): gemini-flash-lite, ~20% of aggressive runs, returns valid+complete
JSON that collapses a 22-item experience list to ~5 — dropping whole roles. Not
a token cutoff (the JSON parses, cover letter present), and neither a bigger
token ceiling nor a "don't drop entries" prompt rule moved the rate. The fix is
a contract-layer guard (ADR-005): retry once, then restore any still-collapsed
section from the original. This test drives that logic with a fake client so it
is deterministic and needs no network.

Runs without pytest:
    .venv/bin/python tests/test_rewrite_fidelity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.settings as settings  # noqa: E402
from core.llm import rewrite  # noqa: E402
from core.llm.rewrite import _collapsed_sections, rewrite_resume  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class FakeClient:
    """Returns queued responses in order; repeats the last one if drained.
    Records how many times generate_json was called."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = 0

    def generate_json(self, prompt, **kwargs):
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return resp


def _resume(n_exp: int) -> dict:
    return {
        "contact": {"name": "Test User", "location": "Bogota"},
        "sections": {
            "experience": [f"Role {i} | Co | 2020" for i in range(n_exp)],
            "skills": ["Python", "SQL", "PM"],
        },
    }


def _resp(n_exp: int) -> dict:
    return {
        "sections": {
            "experience": [f"Tailored {i}" for i in range(n_exp)],
            "skills": ["Python", "SQL", "PM"],
        },
        "cover_letter": "Dear Hiring Manager, ...",
        "notes": "tailored",
        "warnings": [],
    }


def main() -> int:
    # Pure predicate first — the threshold behaviour.
    _assert(_collapsed_sections({"experience": ["a"] * 22}, {"experience": ["x"] * 5}) == ["experience"],
            "22 -> 5 must count as collapsed")
    _assert(_collapsed_sections({"experience": ["a"] * 22}, {"experience": ["x"] * 22}) == [],
            "22 -> 22 is not collapsed")
    _assert(_collapsed_sections({"experience": ["a"] * 22}, {"experience": ["x"] * 14}) == [],
            "22 -> 14 (>=60%) is legitimate trimming, not collapse")
    _assert(_collapsed_sections({"experience": ["a"] * 3}, {"experience": []}) == [],
            "tiny sections (orig <4) are exempt — ratio is meaningless")

    orig = settings.get_output_language
    settings.get_output_language = lambda: "en"
    try:
        # Case 1: first response collapses, retry recovers → keep the retried
        # full version, exactly TWO calls, no restore needed.
        client = FakeClient([_resp(5), _resp(22)])
        out = rewrite_resume(_resume(22), "JD", "aggressive", client, persona="a candidate")
        _assert(client.calls == 2, f"expected retry (2 calls), got {client.calls}")
        _assert(len(out["sections"]["experience"]) == 22,
                f"retry should have recovered 22 items, got {len(out['sections']['experience'])}")

        # Case 2: collapses on BOTH the initial call and the retry → restore
        # the experience section verbatim from the original resume.
        client = FakeClient([_resp(5), _resp(5)])
        out = rewrite_resume(_resume(22), "JD", "aggressive", client, persona="a candidate")
        _assert(client.calls == 2, f"one retry then give up = 2 calls, got {client.calls}")
        _assert(len(out["sections"]["experience"]) == 22,
                "still-collapsed section must be restored from original")
        _assert(out["sections"]["experience"][0].startswith("Role 0"),
                "restored content should be the ORIGINAL text, not the tailored stub")

        # Case 3: healthy first response → no retry, single call.
        client = FakeClient([_resp(22)])
        out = rewrite_resume(_resume(22), "JD", "aggressive", client, persona="a candidate")
        _assert(client.calls == 1, f"healthy output needs no retry, got {client.calls} calls")
        _assert(len(out["sections"]["experience"]) == 22, "healthy output preserved")
    finally:
        settings.get_output_language = orig

    print("OK — rewrite fidelity guard: collapse detected, retried, restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
