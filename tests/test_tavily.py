"""Tavily company search (ADR-029 / GOV-007). No network — httpx.post is
monkeypatched. Locks down: no key → None; a good response assembles the
briefing (answer + snippets) and de-dupes sources; empty results → None; an
HTTP error → None (caller degrades to the honest fallback, never fabricates).

    .venv/bin/python tests/test_tavily.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.prep import tavily  # noqa: E402

_REAL_POST = tavily.httpx.post


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _Resp:
    def __init__(self, data, raise_exc=None):
        self._data = data
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._data


def _patch(data=None, raise_exc=None):
    def fake_post(url, json=None, timeout=None):
        return _Resp(data or {}, raise_exc=raise_exc)
    tavily.httpx.post = fake_post  # type: ignore


def test_no_key_returns_none(monkeypatch_env=None):
    tavily.api_key = lambda: ""  # type: ignore
    _assert(tavily.search_company("CMHC") is None, "no key → None")
    print("PASS test_no_key_returns_none")


def test_good_response_assembles_briefing():
    tavily.api_key = lambda: "k"  # type: ignore
    _patch({
        "answer": "CMHC is Canada's housing agency.",
        "results": [
            {"title": "About", "content": "Public, compliance-heavy.", "url": "https://a.example"},
            {"title": "News", "content": "Launched AI Housing Assist.", "url": "https://b.example"},
            {"title": "Dup", "content": "More.", "url": "https://a.example"},  # dup url
        ],
    })
    r = tavily.search_company("CMHC", "Analyst")
    _assert(r is not None, "should return a result")
    _assert("CMHC is Canada's housing agency." in r.briefing, "answer included")
    _assert("Public, compliance-heavy." in r.briefing and "AI Housing Assist" in r.briefing,
            "snippets included")
    _assert(r.sources == ["https://a.example", "https://b.example"],
            f"sources deduped/ordered, got {r.sources}")
    print("PASS test_good_response_assembles_briefing")


def test_empty_results_returns_none():
    tavily.api_key = lambda: "k"  # type: ignore
    _patch({"answer": "", "results": []})
    _assert(tavily.search_company("Ghost") is None, "no answer + no results → None")
    print("PASS test_empty_results_returns_none")


def test_http_error_returns_none():
    tavily.api_key = lambda: "k"  # type: ignore
    _patch(raise_exc=RuntimeError("500"))
    _assert(tavily.search_company("CMHC") is None, "HTTP error → None")
    print("PASS test_http_error_returns_none")


if __name__ == "__main__":
    try:
        test_no_key_returns_none()
        test_good_response_assembles_briefing()
        test_empty_results_returns_none()
        test_http_error_returns_none()
        print("all tavily tests passed")
    finally:
        tavily.httpx.post = _REAL_POST  # type: ignore
