"""Answer-card interviewer judge (ADR-058 Phase 4): the pure parts — flattening
v2 prose / v3 skeleton cards and parsing the verdict defensively.

Runs without pytest:
    .venv/bin/python tests/test_answer_judge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prep import answer_judge as AJ  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    _assert(AJ.card_text({"answer": " I led it. "}) == "I led it.", "v2 prose used as-is")
    t = AJ.card_text({"frame": [{"section": "approach", "points": ["I split opex [[hint: cadence]]", "owners"]}],
                      "point_to_land": "I own budgets"})
    _assert("approach: I split opex [MISSING: cadence] / owners" in t, f"skeleton flattened, hint marked: {t!r}")
    _assert("point to land: I own budgets" in t, "point to land included")

    v = AJ._parse({"answers_the_question": "yes", "specificity": 9, "filler_phrases": ["rigorous", ""],
                   "invented_facts": "not a list", "one_liner": "  vague\n  approach "}, "m")
    _assert(v and v.answers_the_question and v.specificity == 5, "bool coerced, specificity clamped")
    _assert(v.filler_phrases == ["rigorous"] and v.invented_facts == [], "lists cleaned")
    _assert(v.one_liner == "vague approach", "whitespace collapsed")
    _assert(AJ._parse({"specificity": 3}, "m") is None, "missing verdict → None (skipped, never a fake pass)")
    _assert(AJ._parse("nope", "m") is None, "garbage → None")
    print("OK — answer judge verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
