#!/usr/bin/env python3
"""Weekly canary: verify per-ATS adapters still extract usable data.

Runs in CI (see `.github/workflows/probe-adapters.yml`) once a week, and
on demand. Exits non-zero on any regression so the workflow flags it.

Strategy per ATS: hit the public LIST endpoint, pick the first job id,
construct a job URL, run our adapter's `fetch()`. Assert non-empty
title + company + description.

Why LIST-then-fetch instead of hardcoded job URLs: individual postings
come and go every week. A canary keyed on a specific ID silently rots
when the posting closes, giving us false positives that look like
adapter breakage. LIST-then-fetch stays green as long as at least one
job exists on the tenant.

Exit codes:
    0  — all adapters returned usable data
    1  — one or more adapters failed extraction OR the check itself errored

Run locally:
    ./scripts/probe_adapters.py
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Callable, Optional

# Make `core` importable when run as `python scripts/probe_adapters.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from core.jobs.ats.base import DEFAULT_UA
from core.jobs.ats.greenhouse import GreenhouseAdapter
from core.jobs.ats.lever import LeverAdapter
from core.jobs.ats.oracle_hcm import OracleHcmAdapter


# ── tenants + list-endpoint URL builders ──────────────────────────────

# Long-lived tenants likely to always have >=1 open posting. If any of
# these companies goes dark, swap in another well-known user of the ATS.
GREENHOUSE_BOARD = "stripe"        # boards.greenhouse.io/stripe
LEVER_SLUG = "spotify"             # jobs.lever.co/spotify — 100+ postings, stable tenant
ORACLE_HOST = "fa-evcg-saasfaprod1.fa.ocs.oraclecloud.com"   # BGIS
ORACLE_SITE = "CX_1"


UA_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get_json(url: str, extra_headers: Optional[dict] = None, timeout: float = 15) -> dict:
    headers = dict(UA_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ── probes ────────────────────────────────────────────────────────────

def probe_greenhouse() -> str:
    """Fetch first job from the Greenhouse test board, verify our adapter
    extracts title/company/description. Returns a status line."""
    data = _http_get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{GREENHOUSE_BOARD}/jobs"
    )
    jobs = data.get("jobs") or []
    if not jobs:
        raise RuntimeError(f"No jobs listed on Greenhouse board {GREENHOUSE_BOARD!r}")
    job_id = jobs[0].get("id")
    url = f"https://boards.greenhouse.io/{GREENHOUSE_BOARD}/jobs/{job_id}"
    result = GreenhouseAdapter().fetch(url)
    _assert_usable("greenhouse", result)
    return f"greenhouse: OK — {result['title'][:60]!r} @ {result['company']!r}"


def probe_lever() -> str:
    data = _http_get_json(f"https://api.lever.co/v0/postings/{LEVER_SLUG}?mode=json")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"No postings on Lever slug {LEVER_SLUG!r}")
    post_id = data[0].get("id")
    url = f"https://jobs.lever.co/{LEVER_SLUG}/{post_id}"
    result = LeverAdapter().fetch(url)
    _assert_usable("lever", result)
    return f"lever: OK — {result['title'][:60]!r} @ {result['company']!r}"


def probe_oracle_hcm() -> str:
    """Use the recruiting finder to grab any open req id, then run our
    adapter against a constructed CE URL.

    The `findReqs` finder returns a search-wrapper object, not a raw
    requisition list — the actual jobs live at
    `items[0].requisitionList[]` (only when `expand=all` is set)."""
    listing = _http_get_json(
        f"https://{ORACLE_HOST}/hcmRestApi/resources/latest/"
        f"recruitingCEJobRequisitions?finder=findReqs;siteNumber={ORACLE_SITE}"
        f"&limit=1&onlyData=true&expand=all",
        extra_headers={"ora-irc-language": "en"},
    )
    items = listing.get("items") or []
    if not items:
        raise RuntimeError(
            f"No requisitions on Oracle HCM tenant {ORACLE_HOST!r} site {ORACLE_SITE!r}"
        )
    reqs = items[0].get("requisitionList") or []
    if not reqs:
        raise RuntimeError(
            f"Oracle HCM finder returned no requisitionList — response shape may have changed. "
            f"Top-level item keys: {list(items[0].keys())[:20]}"
        )
    req_id = reqs[0].get("Id") or reqs[0].get("RequisitionId")
    if not req_id:
        raise RuntimeError(f"Oracle HCM first requisition missing Id: {list(reqs[0].keys())[:15]}")
    url = (
        f"https://{ORACLE_HOST}/hcmUI/CandidateExperience/en/sites/"
        f"{ORACLE_SITE}/job/{req_id}/"
    )
    result = OracleHcmAdapter().fetch(url)
    _assert_usable("oracle_hcm", result)
    return f"oracle_hcm: OK — {result['title'][:60]!r} @ {result['company']!r}"


PROBES: list[tuple[str, Callable[[], str]]] = [
    ("greenhouse", probe_greenhouse),
    ("lever", probe_lever),
    ("oracle_hcm", probe_oracle_hcm),
]


# ── shared assertions ─────────────────────────────────────────────────

def _assert_usable(name: str, result: dict) -> None:
    """A job dict is 'usable' if it has non-empty title, company, and
    description. Everything else is optional. Fails loudly with the exact
    field that came back empty — so a fix targets the right thing."""
    for field, min_len in [("title", 3), ("company", 1), ("description", 50)]:
        value = result.get(field, "")
        if not isinstance(value, str) or len(value) < min_len:
            raise AssertionError(
                f"{name} adapter returned unusable {field!r}: "
                f"{value!r} (len={len(value) if isinstance(value, str) else 'n/a'}, min={min_len})"
            )


# ── entrypoint ────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ATS adapter canary probes")
    parser.add_argument(
        "--only",
        choices=[name for name, _ in PROBES],
        help="Run only one probe (for debugging).",
    )
    args = parser.parse_args(argv)

    probes = [
        (name, fn) for name, fn in PROBES
        if not args.only or name == args.only
    ]

    print(f"Running {len(probes)} probe(s)…\n")
    failures: list[str] = []
    for name, fn in probes:
        try:
            print(fn())
        except Exception as exc:  # noqa: BLE001 — canary catches everything
            print(f"{name}: FAIL — {type(exc).__name__}: {exc}")
            traceback.print_exc()
            failures.append(name)

    print()
    if failures:
        print(f"❌ {len(failures)} probe(s) failed: {', '.join(failures)}")
        return 1
    print("✅ All probes passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
