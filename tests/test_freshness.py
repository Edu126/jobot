"""REQ-033: a job with no publisher date must NOT freeze at "≤24h / hoy".

`_coerce_date` now falls back to the fetch date when the publisher omits a
date (common for LinkedIn), so the card shows a real, aging date instead of a
label that never moves.

Runs without pytest:
    .venv/bin/python tests/test_freshness.py
"""
from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.jobs.search import _coerce_date  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    FETCH = "2026-09-08"

    # Missing / unparseable values fall back to the fetch date, never "".
    _assert(_coerce_date(None, fetch_date=FETCH) == FETCH,
            "None must fall back to fetch_date")
    _assert(_coerce_date(float("nan"), fetch_date=FETCH) == FETCH,
            "NaN must fall back to fetch_date")
    _assert(_coerce_date("NaT", fetch_date=FETCH) == FETCH,
            "'NaT' string must fall back to fetch_date")
    _assert(_coerce_date("nan", fetch_date=FETCH) == FETCH,
            "'nan' string must fall back to fetch_date")
    _assert(_coerce_date("", fetch_date=FETCH) == FETCH,
            "empty string must fall back to fetch_date")

    # A real date is preserved (first 10 chars, YYYY-MM-DD).
    _assert(_coerce_date("2026-07-01T00:00:00", fetch_date=FETCH) == "2026-07-01",
            "ISO datetime string must keep its own date")
    _assert(_coerce_date(datetime(2026, 7, 1), fetch_date=FETCH) == "2026-07-01",
            "datetime must keep its own date")

    # Back-compat: no fetch_date given → empty string (old behaviour, no crash).
    _assert(_coerce_date(None) == "", "no fetch_date → empty, not error")

    print("OK — REQ-033 date fallback holds; no frozen '≤24h'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
