"""Contact details never reach an AI provider (ADR-084).

Runs without pytest:
    .venv/bin/python tests/test_redact.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.redact import redact  # noqa: E402


def main() -> int:
    cv = ("Sam Lee\nsam.lee+jobs@mail.co.uk | (613) 555-0101 | +1 416.555.0199 | 6135550123\n"
          "linkedin.com/in/sam-lee-42 · https://github.com/samlee\n"
          "Analyst at Acme, 2019-2024. Cut overtime 25% across 1,200 staff; budget $4,500,000.\n"
          "Source: https://acme.com/about")
    out = redact(cv)
    for leaked in ("sam.lee", "555-0101", "555.0199", "6135550123", "linkedin.com/in", "github.com/samlee"):
        assert leaked not in out, f"{leaked!r} leaked: {out}"
    for kept in ("Sam Lee", "2019-2024", "25%", "1,200", "$4,500,000", "https://acme.com/about"):
        assert kept in out, f"{kept!r} should stay: {out}"
    assert redact("") == "" and redact(None) is None
    print("OK — redact strips email/phone/profile links, keeps name, numbers and source links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
