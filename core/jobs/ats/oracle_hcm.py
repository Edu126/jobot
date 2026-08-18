"""Oracle HCM Cloud (Fusion Recruiting / Candidate Experience) adapter.

The Candidate Experience UI is a SPA — the HTML shell is empty. The real
data lives at:
    GET https://{tenant}.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/
        recruitingCEJobRequisitionDetails/{id}?onlyData=true&expand=all

Note the `Details` suffix — `/recruitingCEJobRequisitions/{id}` returns
404 on this endpoint; the `Details` collection is what CE actually reads.

Company name isn't on the requisition object (LegalEmployer / Organization
are typically null on this endpoint). Instead we hit
    GET https://{tenant}.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/
        recruitingCESites/{site}
and use `SiteName`, stripping trailing " Careers" / " Jobs" — e.g.
`SiteName='BGIS Careers'` → company `'BGIS'`. Results are cached in-process
per (tenant, site) so we don't add a second network hop per import.

URL shape:
    https://{tenant}.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/{lang}/
        sites/{site}/job/{id}/…

Tenant subdomains look like `fa-evcg-saasfaprod1` — treat as opaque;
different customers get different Oracle Fusion pods.

Docs: https://docs.oracle.com/en/cloud/saas/human-resources/farws/op-recruitingicejobrequisitions-get.html
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from .base import AdapterFetchError, guarded_get, html_to_markdown_lite, raw_to_job_dict


_HOST_RE = re.compile(r"^[a-zA-Z0-9-]+\.fa\.ocs\.oraclecloud\.com$")
_PATH_RE = re.compile(
    r"/sites/(?P<site>[A-Za-z0-9_-]+)/job/(?P<id>[A-Za-z0-9_-]+)"
)

# Small in-process cache: {(host, site): "Company Name"}. Never grows past
# a handful of entries per process lifetime — Oracle HCM tenants are stable.
_SITE_COMPANY_CACHE: dict[tuple[str, str], str] = {}


class OracleHcmAdapter:
    name = "oracle_hcm"

    def matches(self, url: str) -> bool:
        try:
            p = urlparse(url or "")
        except Exception:
            return False
        if not p.hostname or not _HOST_RE.match(p.hostname):
            return False
        return "/hcmUI/" in (p.path or "") and bool(_PATH_RE.search(p.path or ""))

    def fetch(self, url: str) -> dict:
        p = urlparse(url)
        host = p.hostname or ""
        m = _PATH_RE.search(p.path or "")
        if not m:
            raise AdapterFetchError(f"No site/job segment in URL: {url}")
        site = m.group("site")
        job_id = m.group("id")

        api = (
            f"https://{host}/hcmRestApi/resources/latest/"
            f"recruitingCEJobRequisitionDetails/{job_id}?onlyData=true&expand=all"
        )
        resp = guarded_get(
            api,
            headers={
                "Accept": "application/json",
                "ora-irc-language": "en",
            },
        )
        data = resp.json()

        title = data.get("Title") or data.get("OtherRequisitionTitle") or ""
        location = data.get("PrimaryLocation") or ""

        # Stitch the three narrative fields when present. Most tenants put
        # everything in ExternalDescriptionStr; some split responsibilities
        # and qualifications into separate fields.
        parts = [
            data.get("ExternalDescriptionStr"),
            data.get("ExternalResponsibilitiesStr"),
            data.get("ExternalQualificationsStr"),
        ]
        description = html_to_markdown_lite("\n".join(p for p in parts if p))

        posted = _first_date(
            data.get("ExternalPostedStartDate"),
            data.get("PostedDate"),
        )

        company = _resolve_company(host, site, data)

        raw = {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "is_remote": _looks_remote(location, description, data),
            "posted_date": posted,
            "job_url_direct": url,   # the CE page IS the apply URL
        }
        return raw_to_job_dict(raw, source_url=url, site_hint="oracle_hcm")


# ── helpers ────────────────────────────────────────────────────────────

def _first_date(*values: Optional[str]) -> str:
    """Return the YYYY-MM-DD prefix of the first ISO-ish datetime seen."""
    for v in values:
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return ""


_COMPANY_SUFFIX_RE = re.compile(
    r"\s+(careers|jobs|talent|opportunities|hiring)$", re.IGNORECASE
)


def _resolve_company(host: str, site: str, req_data: dict) -> str:
    """Company-name fallback chain:
        1. RequisitionEmployer / LegalEmployer / Organization from the
           requisition (usually null on CE endpoint but check anyway).
        2. SiteName from recruitingCESites/{site}, with common suffixes
           stripped (`'BGIS Careers'` → `'BGIS'`).
        3. Tenant slug titlecased (ugly last resort)."""
    for k in ("RequisitionEmployer", "LegalEmployer", "Organization", "OrganizationName"):
        v = req_data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    cached = _SITE_COMPANY_CACHE.get((host, site))
    if cached:
        return cached

    site_url = (
        f"https://{host}/hcmRestApi/resources/latest/recruitingCESites/{site}"
    )
    try:
        resp = guarded_get(site_url, headers={"Accept": "application/json"})
        site_data = resp.json()
    except Exception:  # noqa: BLE001 — company lookup is best-effort
        site_data = {}

    name = (site_data.get("SiteName") or site_data.get("SiteCode") or "").strip()
    if name:
        clean = _COMPANY_SUFFIX_RE.sub("", name).strip()
        clean = clean or name
        _SITE_COMPANY_CACHE[(host, site)] = clean
        return clean

    return _tenant_to_company(host)


def _tenant_to_company(host: str) -> str:
    """Last-resort fallback when SiteName lookup fails too."""
    sub = host.split(".")[0]
    core = sub.replace("saasfaprod1", "").rstrip("-")
    return core.replace("-", " ").title() or "Oracle Employer"


def _looks_remote(location: str, description: str, data: dict) -> bool:
    if data.get("RemoteWorkAllowed") is True:
        return True
    wtc = data.get("WorkplaceTypeCode") or data.get("WorkplaceType")
    if isinstance(wtc, str) and "REMOTE" in wtc.upper():
        return True
    blob = f"{location} {description}".lower()
    return any(kw in blob for kw in ("remote", "work from home", "telework"))
