"""Fixture test for the AI-summary grounding validator.

The bug this locks down: the model wrote "sudden pivot to art gallery
work feels totally random and unconvincing" for a resume with zero
art or gallery content. Previously we had no server-side check that
the impression's specific claims matched the resume — the only
defense was a "Regenerate" button that trained users to distrust
output and invited spam.

Post-fix (2026-08-20): `_validate_grounded` requires every
first_impression_evidence snippet to appear (normalized) in the
resume text. A "specific claim" impression with no evidence fails.
This test locks both invariants.

Runs without pytest:
    .venv/bin/python tests/test_ai_summary_grounding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui_web.routes.profile import (  # noqa: E402
    _ResumeSummaryLLM,
    _validate_grounded,
    _looks_specific,
    _normalize_for_grounding,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


RESUME = """
Sara Álvarez Ordoñez
Barcelona, Spain

Experience:
- Marketing Manager at Acme Corp (2020-present). Led B2B campaigns for
  European accounts. Grew MQL pipeline 40% year-over-year.
- Senior Marketing Analyst at Widgets SA (2017-2020). Owned attribution
  modeling and quarterly board reporting.

Education:
- BA Marketing, Universidad de Barcelona (2016)

Skills: Google Analytics, HubSpot, SQL, Spanish (native), English (C2).
""".strip()


def _mk(imp: str, ev: list[str]) -> _ResumeSummaryLLM:
    return _ResumeSummaryLLM(
        role_label="marketing",
        first_impression=imp,
        first_impression_evidence=ev,
        section_suggestions=[],
    )


def main() -> int:
    # _validate_grounded now takes the pre-normalized resume text (the
    # normalization is hoisted out of the loop for reuse across retries).
    # Compute once here so test fixtures pass what production passes.
    RESUME_NORM = _normalize_for_grounding(RESUME)

    # 1. GOOD — impression cites specific facts, evidence is verbatim.
    good = _mk(
        "Solid B2B marketing background with measurable pipeline growth at Acme Corp.",
        ["Marketing Manager at Acme Corp", "Grew MQL pipeline 40%"],
    )
    _assert(_validate_grounded(good, RESUME_NORM),
            "grounded impression + verbatim evidence should PASS")

    # 2. BAD — the art-gallery pattern. Specific claim about a thing not in resume.
    bad_art_gallery = _mk(
        "Big multinational brands here, but the sudden pivot to art gallery work feels totally random.",
        ["art gallery work"],   # this snippet is nowhere in the resume
    )
    _assert(not _validate_grounded(bad_art_gallery, RESUME_NORM),
            "art-gallery hallucination MUST fail grounding")

    # 3. BAD — specific-looking impression with NO evidence at all.
    bad_no_evidence = _mk(
        "Impressive tenure at Acme Corp with a technical marketing focus.",
        [],
    )
    _assert(not _validate_grounded(bad_no_evidence, RESUME_NORM),
            "specific claim with zero evidence MUST fail")

    # 4. GOOD — generic impression, no evidence needed.
    good_generic = _mk(
        "solid mid-career resume, no red flags",
        [],
    )
    _assert(_validate_grounded(good_generic, RESUME_NORM),
            "generic impression with empty evidence should PASS")

    # 5. BAD — evidence exists but doesn't appear in resume (paraphrased).
    bad_paraphrase = _mk(
        "Grew pipeline 40 percent year over year at Acme Corp.",
        ["Grew pipeline by forty percent yearly at Acme"],   # paraphrase
    )
    _assert(not _validate_grounded(bad_paraphrase, RESUME_NORM),
            "paraphrased evidence (not verbatim) MUST fail")

    # 6. BAD — evidence snippet too short (below _EVIDENCE_MIN_CHARS).
    bad_short = _mk(
        "Marketing Manager at Acme.",
        ["Acme"],   # 4 chars < 6-char minimum
    )
    _assert(not _validate_grounded(bad_short, RESUME_NORM),
            "sub-minimum evidence snippet MUST fail")

    # 7. BAD — evidence snippet too long (regurgitation).
    bad_long = _mk(
        "Extensive experience.",
        [RESUME],   # entire resume as evidence — regurgitation
    )
    _assert(not _validate_grounded(bad_long, RESUME_NORM),
            "over-max evidence snippet MUST fail")

    # 8. Whitespace tolerance — resume has line breaks; evidence with a
    # single space should still match.
    tolerant = _mk(
        "Board-facing analytics work at Widgets SA.",
        ["Owned attribution modeling and quarterly board reporting"],
    )
    _assert(_validate_grounded(tolerant, RESUME_NORM),
            "whitespace-tolerant match should PASS")

    # 9. _looks_specific heuristic — sanity check.
    _assert(_looks_specific("Big campaigns at Acme Corp"),
            "proper noun should trigger specific-claim heuristic")
    _assert(_looks_specific("40% pipeline growth"),
            "digits should trigger specific-claim heuristic")
    _assert(not _looks_specific("solid mid-career resume, no red flags"),
            "generic prose should not trigger specific-claim heuristic")

    print("OK — grounding validator holds on 9 fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
