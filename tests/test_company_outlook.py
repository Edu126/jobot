"""Company outlook two-hop + cache (REQ-023 / ADR-027). Locks down:
  1. a miss runs hop 1 (grounded) then hop 2 (structuring) and returns the
     3 facets + news + sources;
  2. the result is cached — a second call does NOT re-run either hop;
  3. use_cache=False (the "Refresh news intel" path) DOES re-run;
  4. the cache key is normalized — "CMHC Inc." and "cmhc" share one row;
  5. an empty grounded briefing → None (grounded-or-none, nothing fabricated);
  6. hop-2 failure → None.

No network: hop 1 (`company_research.fetch_company_context`) is monkeypatched
and hop 2 uses a fake GeminiClient. Runs without pytest:
    .venv/bin/python tests/test_company_outlook.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.llm import company_research  # noqa: E402
from core.prep import company_outlook as co  # noqa: E402


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeClient:
    """Stands in for GeminiClient — records hop-2 calls, returns a canned
    structured payload (or raises to simulate failure)."""
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


_HOP1 = company_research.CompanyResearch(
    summary=("CMHC is Canada's national housing agency: a public, risk-averse, "
             "compliance-heavy organization. It is investing in housing "
             "affordability technology and cloud data pipelines. In July 2026 it "
             "launched an AI Housing Assist tool."),
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

# Preserve the real function so tests that need it can restore.
_REAL_FETCH = company_research.fetch_company_context


def _fresh() -> Path:
    p = Path(tempfile.mkdtemp()) / "co.sqlite"
    db.init_db(p)
    return p


def _patch_hop1(calls_box, summary=None):
    def fake(api_key, company, role_title="", model_name="", lang=""):
        calls_box.append((company, role_title, lang))
        if summary is not None:
            return company_research.CompanyResearch(summary=summary, sources=[])
        return _HOP1
    company_research.fetch_company_context = fake  # type: ignore


def test_two_hop_miss_then_cache():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)

    out = co.get_or_generate("CMHC", "Senior Business Analyst", client, "key",
                             lang="en", path=p)
    _assert(out is not None, "miss should produce an outlook")
    _assert(out.culture_tone.startswith("Public agency"), f"culture_tone wrong: {out.culture_tone!r}")
    _assert(out.strategic_focus.startswith("Housing affordability"), "strategic_focus wrong")
    _assert(len(out.recent_news) == 1 and out.recent_news[0].headline == "Launched AI Housing Assist",
            "news not structured")
    _assert(out.sources == _HOP1.sources, "sources pass through from hop 1")
    _assert(len(hop1) == 1 and client.calls == 1, "miss runs each hop once")
    _assert(out.verified_at, "verified_at set from the stored row")
    print("PASS test_two_hop_miss_then_cache")


def test_cache_hit_skips_both_hops():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC", "BA", client, "key", lang="en", path=p)
    out2 = co.get_or_generate("CMHC", "BA", client, "key", lang="en", path=p)
    _assert(out2 is not None and not out2.is_empty(), "cache hit returns the outlook")
    _assert(len(hop1) == 1 and client.calls == 1, "cache hit must not re-run either hop")
    print("PASS test_cache_hit_skips_both_hops")


def test_refresh_reruns():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC", "BA", client, "key", lang="en", path=p)
    co.get_or_generate("CMHC", "BA", client, "key", lang="en", use_cache=False, path=p)
    _assert(len(hop1) == 2 and client.calls == 2, "refresh (use_cache=False) re-runs both hops")
    print("PASS test_refresh_reruns")


def test_cache_key_normalized():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1)
    client = _FakeClient(payload=_HOP2)
    co.get_or_generate("CMHC Inc.", "BA", client, "key", lang="en", path=p)
    out = co.get_or_generate("cmhc", "BA", client, "key", lang="en", path=p)
    _assert(out is not None, "normalized form should hit the cache")
    _assert(len(hop1) == 1, f"normalized company shares a row; hop1 ran {len(hop1)}x")
    print("PASS test_cache_key_normalized")


def test_empty_briefing_returns_none():
    p = _fresh()
    hop1: list = []
    _patch_hop1(hop1, summary="   ")
    client = _FakeClient(payload=_HOP2)
    out = co.get_or_generate("Ghost Co", "BA", client, "key", lang="en", path=p)
    _assert(out is None, "empty briefing yields None (grounded-or-none)")
    _assert(client.calls == 0, "hop 2 must not run when hop 1 is empty")
    print("PASS test_empty_briefing_returns_none")


def test_hop2_failure_returns_none():
    p = _fresh()
    _patch_hop1([])
    client = _FakeClient(raise_exc=company_research.GeminiError("boom"))
    out = co.get_or_generate("CMHC", "BA", client, "key", lang="en", path=p)
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
        company_research.fetch_company_context = _REAL_FETCH  # type: ignore
