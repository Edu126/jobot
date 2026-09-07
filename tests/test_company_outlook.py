"""Company outlook two-hop + cache (REQ-023 / ADR-027; search hop = Tavily per
ADR-029). Locks down:
  1. a miss runs hop 1 (Tavily search) then hop 2 (Gemini structuring) and
     returns the 3 facets + news + sources;
  2. the result is cached — a second call does NOT re-run either hop;
  3. use_cache=False (the "Refresh news intel" path) DOES re-run;
  4. the cache key is normalized — "CMHC Inc." and "cmhc" share one row;
  5. an empty Tavily briefing → None (grounded-or-none, nothing fabricated);
  6. hop-2 failure → None.

No network: hop 1 (`tavily.search_company`) is monkeypatched and hop 2 uses a
fake GeminiClient. Runs without pytest:
    .venv/bin/python tests/test_company_outlook.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm.gemini import GeminiError  # noqa: E402
from core.prep import company_outlook as co  # noqa: E402
from core.prep import tavily  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeClient:
    """Stands in for GeminiClient (hop 2) — records structuring calls, returns a
    canned payload (or raises to simulate failure)."""
    def __init__(self, payload=None, raise_exc=None):
        self.payload = payload
        self.raise_exc = raise_exc
        self.calls = 0
        self.last_model_used = "fake-model"
        self.model_name = "fake-model"

    def all_models_exhausted(self):
        return False

    def generate_json(self, prompt, *, temperature=None, max_retries=2):
        self.calls += 1
        if self.raise_exc:
            raise self.raise_exc
        return self.payload


_HOP1 = tavily.TavilyResult(
    briefing=("CMHC is Canada's national housing agency: public, risk-averse, "
              "compliance-heavy. Investing in housing affordability technology "
              "and cloud data pipelines. In July 2026 it launched AI Housing Assist."),
    sources=["https://cmhc.example/press/ai-housing-assist"],
)

_HOP2 = {
    "culture_tone": "Public agency, risk-averse, compliance- and data-heavy.",
    "strategic_focus": "Housing affordability tech and cloud data pipelines.",
    "recent_news": [
        {"headline": "Launched AI Housing Assist", "date": "Jul 2026",
         "url": "https://cmhc.example/press/ai-housing-assist"},
    ],
}

_REAL_SEARCH = tavily.search_company


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "co.sqlite"
    db.init_db(p)
    return p


def _patch_hop1(calls_box, briefing=None):
    def fake(company, role_title=""):
        calls_box.append((company, role_title))
        if briefing is not None:
            return tavily.TavilyResult(briefing=briefing, sources=[])
        return _HOP1
    tavily.search_company = fake  # type: ignore


def test_two_hop_miss_then_cache():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)

    out = co.get_or_generate("CMHC", "Senior Business Analyst", client,
                             lang="en", path=p)
    _assert(out is not None, "miss should produce an outlook")
    _assert(out.culture_tone.startswith("Public agency"), f"culture_tone wrong: {out.culture_tone!r}")
    _assert(out.strategic_focus.startswith("Housing affordability"), "strategic_focus wrong")
    _assert(len(out.recent_news) == 1 and out.recent_news[0].headline == "Launched AI Housing Assist",
            "news not structured")
    _assert(out.sources == _HOP1.sources, "sources pass through from Tavily")
    _assert(len(hop1) == 1 and client.calls == 1, "miss runs each hop once")
    _assert(out.verified_at, "verified_at set from the stored row")
    print("PASS test_two_hop_miss_then_cache")


def test_cache_hit_skips_both_hops():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC", "BA", client, lang="en", path=p)
    out2 = co.get_or_generate("CMHC", "BA", client, lang="en", path=p)
    _assert(out2 is not None and not out2.is_empty(), "cache hit returns the outlook")
    _assert(len(hop1) == 1 and client.calls == 1, "cache hit must not re-run either hop")
    print("PASS test_cache_hit_skips_both_hops")


def test_refresh_reruns():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC", "BA", client, lang="en", path=p)
    co.get_or_generate("CMHC", "BA", client, lang="en", use_cache=False, path=p)
    _assert(len(hop1) == 2 and client.calls == 2, "refresh (use_cache=False) re-runs both hops")
    print("PASS test_refresh_reruns")


def test_cache_key_normalized():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC Inc.", "BA", client, lang="en", path=p)
    out = co.get_or_generate("cmhc", "BA", client, lang="en", path=p)
    _assert(out is not None, "normalized form should hit the cache")
    _assert(len(hop1) == 1, f"normalized company shares a row; hop1 ran {len(hop1)}x")
    print("PASS test_cache_key_normalized")


def test_empty_briefing_returns_none():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1, briefing="   ")
    client = _FakeClient(payload=_HOP2)
    out = co.get_or_generate("Ghost Co", "BA", client, lang="en", path=p)
    _assert(out is None, "empty briefing yields None (grounded-or-none)")
    _assert(client.calls == 0, "hop 2 must not run when Tavily returns nothing")
    print("PASS test_empty_briefing_returns_none")


def test_hop2_failure_returns_none():
    p = _fresh()
    _patch_hop1([])
    client = _FakeClient(raise_exc=GeminiError("boom"))
    out = co.get_or_generate("CMHC", "BA", client, lang="en", path=p)
    _assert(out is None, "hop-2 failure yields None, never a fabricated card")
    print("PASS test_hop2_failure_returns_none")


if __name__ == "__main__":
    try:
        test_two_hop_miss_then_cache()
        test_cache_hit_skips_both_hops()
        test_refresh_reruns()
        test_cache_key_normalized()
        test_empty_briefing_returns_none()
        test_hop2_failure_returns_none()
        print("all company-outlook tests passed")
    finally:
        tavily.search_company = _REAL_SEARCH  # type: ignore
