"""Tavily search — the company-intel search hop for Prep (ADR-029 / GOV-007).

Replaces Gemini's *Grounding with Google Search* as hop 1 of the company
outlook. Gemini grounding proved quota-fragile on the free tier (a 429 made the
outlook fall back for every company); Tavily's free tier is 1,000 searches/month
(no credit card) and is fully decoupled from the Gemini grounding quota. The
Gemini structuring pass (hop 2, ADR-027) is unchanged — it now organizes
Tavily's public snippets instead of a grounded briefing.

Only the company name + role leave the system (GOV-007) — no PII, no résumé.
Absent key / any failure ⇒ returns None ⇒ the honest "no intel" fallback.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

TAVILY_URL = "https://api.tavily.com/search"
MAX_RESULTS = 5
TIMEOUT_S = 15


@dataclass
class TavilyResult:
    briefing: str                       # concatenated snippets for hop-2 to structure
    sources: list[str] = field(default_factory=list)


def api_key() -> str:
    return (os.getenv("TAVILY_API_KEY") or "").strip()


def search_company(company: str, role_title: str = "") -> TavilyResult | None:
    """Fetch public snippets about a company. Returns a briefing blob + source
    URLs, or None when there's no key, no company, or the call/parse fails —
    the caller degrades to the honest fallback (never fabricates)."""
    key = api_key()
    company = (company or "").strip()
    if not key or not company:
        return None

    query = (f"{company} company: what they do, culture and work environment, "
             f"strategic focus, and recent news")
    if role_title.strip():
        query += f" (candidate interviewing for {role_title.strip()})"

    try:
        resp = httpx.post(
            TAVILY_URL,
            json={
                "api_key": key,
                "query": query,
                "search_depth": "basic",
                "max_results": MAX_RESULTS,
                "include_answer": True,
            },
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    parts: list[str] = []
    answer = (data.get("answer") or "").strip()
    if answer:
        parts.append(answer)

    sources: list[str] = []
    for item in (data.get("results") or []):
        if not isinstance(item, dict):
            continue
        content = (item.get("content") or "").strip()
        title = (item.get("title") or "").strip()
        if content:
            parts.append(f"{title}: {content}" if title else content)
        url = (item.get("url") or "").strip()
        if url:
            sources.append(url)

    briefing = "\n\n".join(parts).strip()
    if not briefing:
        return None

    seen: set[str] = set()
    sources = [s for s in sources if not (s in seen or seen.add(s))]
    return TavilyResult(briefing=briefing, sources=sources)
