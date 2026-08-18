# ATS Extraction Pipeline — Research

**Status:** research doc, no code yet. See section 7 for what to build.
**Date:** 2026-08-17

## 1. Why this exists

`core/jobs/from_url.py` currently uses a single fallback path for every URL:
`requests.get()` → strip HTML → hand raw text to Gemini for extraction. That
works for server-rendered pages (Greenhouse, Lever) but silently fails on SPAs
that render job content client-side. The concrete failing case:

```
https://fa-evcg-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/232268/?...
```

Fetching that URL with `requests` returns an empty SPA shell — no title, no
description, nothing for the LLM to extract. The page's actual data lives at a
different URL, hit via XHR after the shell loads.

The fix isn't a better LLM prompt. It's routing per ATS: detect the host,
transform the browser URL into the ATS's real data endpoint, hit that
endpoint, and only fall back to LLM extraction when we don't recognize the
host.

## 2. Market ranking (2025-2026)

Two overlapping rankings matter:
- **By employer count** — how many companies use it. Dominated by
  Greenhouse (~49% of top-rated employers per ResumeGeni's 2026 survey),
  Workday (~22%), Lever (~8%).
- **By enterprise footprint** — how many Fortune 500 use it. Workday, Oracle
  (HCM Cloud + legacy Taleo), SAP SuccessFactors, iCIMS lead here.

Combined top 10 to target (roughly ordered by prevalence of URLs a Canadian
job seeker will paste into jobot-app):

| # | System | Notable | Extraction difficulty |
|---|--------|---------|----------------------|
| 1 | **Workday** | Every mid-large enterprise. `myworkdayjobs.com` | Medium — needs POST to `/wday/cxs/…` |
| 2 | **Oracle HCM Cloud** | Absorbed Taleo tenants. `oraclecloud.com/hcmUI` | Medium — REST endpoint with headers |
| 3 | **Greenhouse** | Tech / startups. `boards.greenhouse.io` | Easy — public JSON API |
| 4 | **Lever** | Tech / startups. `jobs.lever.co` | Easy — public JSON API |
| 5 | **iCIMS** | Enterprise + government. `*.icims.com` | Medium — undocumented but stable |
| 6 | **SAP SuccessFactors** | Fortune 500 HR. `career.sap.com`-style | Hard — OData, per-tenant auth |
| 7 | **Ashby** | Modern tech (Linear, etc). `jobs.ashbyhq.com` | Easy — public JSON API |
| 8 | **SmartRecruiters** | Mid-market (SAP acquired 2025). `smartrecruiters.com` | Easy — public JSON API |
| 9 | **BambooHR** | SMB. Embedded widget on customer domain | Hard — undocumented, brittle |
| 10 | **Taleo (legacy)** | Still huge in gov/enterprise. `taleo.net` | Hard — query-param URLs, JSP-era HTML |

Sources: [ResumeGeni ATS Market Share 2026](https://resumegeni.com/research/ats-market-share-2026), [Mordor Intelligence ATS market](https://www.mordorintelligence.com/industry-reports/applicant-tracking-system-market), [DEV: every major ATS has a public job feed](https://dev.to/agenticemail/every-major-ats-has-a-public-job-feed-here-is-how-to-read-them-all-3k10).

Notable 2025 consolidation: SAP acquired SmartRecruiters, Workday absorbed
Paradox, iCIMS acquired Apli. Doesn't change the URL shapes yet but worth
tracking — SmartRecruiters URLs may migrate to `career.sap.com` over 2026.

## 3. Per-ATS URL patterns and endpoints

### Workday
- **URL:** `https://{tenant}.wd{N}.myworkdayjobs.com/[locale/]{site}/job/{location}/{title-slug}_{req-id}` (also `{tenant}.myworkday.com`)
- **API:** `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with body `{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}` (list); or `.../jobs/{id}` for detail. Plain `GET` returns 400 — must be POST with correct `Content-Type`.
- **Gotcha:** rate-limits appear to be per source IP across ALL tenants, not per tenant. A 429 on one Workday customer means you've been noisy across the network.
- **Reference:** [JobsPipe Workday guide](https://jobspipe.dev/blog/workday-api-guide), [DEV community writeup](https://dev.to/agenticemail/every-major-ats-has-a-public-job-feed-here-is-how-to-read-them-all-3k10).

### Oracle HCM Cloud (the failing URL)
- **URL:** `https://{tenant}.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/{lang}/sites/{site}/job/{id}/?…`
- **API:** `GET https://{tenant}.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/{id}?onlyData=true&expand=all` — verified working on the BGIS pod. Note the `Details` suffix; `recruitingCEJobRequisitions/{id}` returns 404 on the CE endpoint.
- **Company name lookup:** the requisition object's `LegalEmployer`/`Organization`/`RequisitionEmployer` are typically null. Hit `GET .../recruitingCESites/{site}` and read `SiteName` (strip trailing " Careers"/" Jobs"). Cache per (tenant, site) to avoid a second network hop per job.
- **Headers required:** `Accept: application/json`, `ora-irc-language: en`. `Content-Type: application/vnd.oracle.adf.resourceitem+json;charset=utf-8` is documented but not required for this endpoint. List queries need `finder=findReqs;siteNumber={site}`.
- **Reference:** [Oracle Fusion HCM REST docs](https://docs.oracle.com/en/cloud/saas/human-resources/farws/op-recruitingicejobrequisitions-get.html).

### Greenhouse
- **URL:** `https://boards.greenhouse.io/{board_token}/jobs/{job_id}` (also embedded on customer domains via iframe).
- **API:** `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}` — public, unauthenticated, JSON. List with `?content=true` includes full HTML descriptions.
- **Reference:** [Greenhouse Job Board API docs](https://developers.greenhouse.io/job-board.html).

### Lever
- **URL:** `https://jobs.lever.co/{company_slug}/{posting_id}`
- **API:** `GET https://api.lever.co/v0/postings/{company_slug}?mode=json` (list), `.../postings/{company_slug}/{id}?mode=json` (detail). Public, no auth.
- **Gotcha:** some customers disable the public feed or use vanity domains; endpoint may 404.
- **Reference:** [Lever developer docs](https://hire.lever.co/developer/documentation).

### iCIMS
- **URL:** `https://careers-{company}.icims.com/jobs/{id}/{slug}/job` or vanity `careers.{company}.com`
- **API:** `/api/jobs` on the same host (undocumented but stable). Passing `?in_iframe=1` on the HTML URL returns the job content without the site chrome, which is a decent fallback.
- **Gotcha:** rate-limits per domain; JSON shape shifts across iCIMS releases.
- **Reference:** [Apify iCIMS scraper](https://apify.com/benthepythondev/icims-jobs-scraper), [OpenPostings extraction guide](https://github.com/Masterjx9/OpenPostings/discussions/16).

### SAP SuccessFactors
- **URL:** `https://career.{company}.com/careers/job/{id}` or `https://{tenant}.successfactors.com/career?career_job_req_id={id}`
- **API:** OData v2 at `https://{datacenter-host}/odata/v2/JobRequisition` — requires per-tenant Recruiter Operator OAuth. **Not usable without customer credentials.**
- **Realistic path:** JSON-LD scrape of the public career page HTML. SuccessFactors emits `schema.org/JobPosting` on the SSR HTML.
- **Reference:** [SAP SuccessFactors docs](https://help.sap.com/docs/successfactors-recruiting/setting-up-and-maintaining-sap-successfactors-recruiting/career-sites-for-sap-successfactors-recruiting).

### Ashby
- **URL:** `https://jobs.ashbyhq.com/{slug}/{posting_id}`
- **API:** `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` — public, no auth.
- **Rate limit:** ~100 rpm unofficial; add 500-600 ms between calls.
- **Reference:** [Ashby posting-api scraper writeup](https://apify.com/deadlyaccurate/ashby-jobs-scraper).

### SmartRecruiters
- **URL:** `https://jobs.smartrecruiters.com/{company}/{posting_id}-{slug}` or `https://careers.{company}.com/…`
- **API:** `GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{id}` — public. Also `GET .../v1/companies/{company}/postings` for list.
- **Reference:** [SmartRecruiters Posting API docs](https://developers.smartrecruiters.com/docs/posting-api).

### BambooHR
- **URL:** customer-owned domain hosting the BambooHR careers widget (iframe or JS embed).
- **API:** widget hits an internal JSON endpoint whose host + shape changes across releases. There is **no** stable documented public endpoint. Official BambooHR REST API is auth-only and oriented at HR data, not jobs.
- **Realistic path:** LLM extraction on the widget HTML, or Playwright if the widget is fully client-rendered.

### Taleo (legacy Oracle, pre-HCM Cloud)
- **URL:** `https://{client}.taleo.net/careersection/…/jobdetail.ftl?job={req_id}` or `.../publicurl/viewRequisition?requisitionNumber={id}`.
- **API:** Oracle documents a "TE Job Feed" for licensed partners; not usable ad-hoc. Public path is HTML scraping of `viewRequisition`.
- **Server-rendered**, so `requests` + BeautifulSoup on the `jobdetail.ftl` page works.
- **Reference:** [Oracle Taleo deep-linking docs](https://docs.oracle.com/en/cloud/saas/talent-acquisition/17.6/otrdc/deep-linking-configuration.html).

## 4. Extraction strategy per system

| System | Primary path | Fallback |
|--------|-------------|----------|
| Workday | `POST /wday/cxs/{tenant}/{site}/jobs/{id}` | JSON-LD on the HTML shell |
| Oracle HCM Cloud | `GET /hcmRestApi/.../recruitingCEJobRequisitions/{id}` | LLM on HTML (weak — SPA shell) |
| Greenhouse | `GET boards-api.greenhouse.io/v1/boards/{t}/jobs/{id}` | Server-rendered HTML |
| Lever | `GET api.lever.co/v0/postings/{slug}/{id}?mode=json` | Server-rendered HTML |
| iCIMS | `GET /api/jobs` on host | HTML + `?in_iframe=1` |
| SuccessFactors | JSON-LD on career HTML | LLM on HTML |
| Ashby | `GET api.ashbyhq.com/posting-api/job-board/{slug}` | HTML |
| SmartRecruiters | `GET api.smartrecruiters.com/v1/companies/{c}/postings/{id}` | HTML |
| BambooHR | JSON-LD on widget page | Playwright + LLM |
| Taleo | HTML + BeautifulSoup | LLM fallback |

**Universal fallback: JSON-LD (`schema.org/JobPosting`).** Google for Jobs
gives ATSs a hard incentive to emit it, so most SSR pages already include the
full posting as JSON-LD in a `<script type="application/ld+json">` tag. This
is a cheap first pass that beats LLM extraction for the systems that emit it.
`extruct` (Python lib) parses it in ~5 lines. Details: [schema.org JobPosting](https://schema.org/JobPosting), [SchemaValidator's job-posting guide](https://schemavalidator.org/guides/job-posting-schema-guide).

## 5. Top 3 deep dive — build these first

### Workday — recipe
Input URL: `https://acme.wd5.myworkdayjobs.com/en-US/External/job/San-Francisco/Backend-Engineer_R-1234`

1. Regex parse: `tenant=acme`, `wd=5`, `site=External`, req id from trailing `_R-1234`.
2. Fetch `https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/External/jobs/R-1234` with `POST`, `Content-Type: application/json`, body `{}`.
3. Response fields → our schema: `jobPostingInfo.title` → title, `jobPostingInfo.location` → location, `jobPostingInfo.jobDescription` → description (HTML), `jobPostingInfo.postedOn` → posted_date. Company = tenant slug titlecased (Workday doesn't expose it in the payload; safe to fall back).

Gotcha: some tenants use `myworkday.com` instead of `myworkdayjobs.com`. Add both to the host regex.

### Oracle HCM Cloud — recipe (the failing URL, VERIFIED)
Input URL: `https://fa-evcg-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/232268/?…`

1. Regex parse: `tenant=fa-evcg-saasfaprod1`, `site=CX_1`, `id=232268`.
2. `GET https://fa-evcg-saasfaprod1.fa.ocs.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails/232268?onlyData=true&expand=all`
3. Headers: `Accept: application/json`, `ora-irc-language: en`.
4. Fields → schema: `Title` → title, `PrimaryLocation` → location, `ExternalDescriptionStr` (+ optional `ExternalResponsibilitiesStr` + `ExternalQualificationsStr`) → description (HTML; convert to markdown-lite via `html_to_markdown_lite` before returning), `ExternalPostedStartDate` → posted_date (fall back to `PostedDate`).
5. Company: `RequisitionEmployer` / `LegalEmployer` / `Organization` are usually null on the CE endpoint. Fall back to `GET .../recruitingCESites/{site}` and use `SiteName` (strip " Careers" / " Jobs" suffix). Cache the (tenant, site) → company mapping in-process.

Verified against the BGIS pod (2026-08-17): endpoint returns title "Project Manager", `SiteName='BGIS Careers'` → company `'BGIS'`, `PrimaryLocation='Ottawa, ON, Canada'`, full 6 KB HTML description.

The tenant subdomain `fa-evcg-saasfaprod1` is the customer's Oracle Fusion pod — treat it as opaque; different customers get different pods.

### Greenhouse — recipe
Input URL: `https://boards.greenhouse.io/stripe/jobs/6789012`

1. Regex parse: `board_token=stripe`, `job_id=6789012`.
2. `GET https://boards-api.greenhouse.io/v1/boards/stripe/jobs/6789012?content=true`
3. Fields → schema: `title`, `location.name`, `content` (HTML — full description including responsibilities and requirements), `updated_at` → posted_date, `company_name` → company (falls back to board_token titlecased).

Embedded boards (Greenhouse iframe on customer domain) usually expose the
same `board_token` in the iframe `src`. Regex the parent HTML for
`greenhouse.io/embed/job_board\?for=([^&]+)`.

## 6. Phase 2 (top 5) — add after top 3

Recommended next two:
- **Lever** — trivial to add (same shape as Greenhouse), covers a big slice of the tech job market the user already targets.
- **Ashby** — small but growing fast in modern-stack tech companies, and its API is the simplest of any ATS.

Skip iCIMS and SuccessFactors initially — iCIMS is medium-hard with brittle
JSON, SuccessFactors needs per-tenant auth. Cover them via JSON-LD fallback
until user pastes enough URLs to justify dedicated parsers.

## 7. Cross-cutting infra to add

Currently `from_url.py` does one thing: fetch and hand to LLM. Refactor to a
routing layer:

```
core/jobs/ats/
  __init__.py          # registry: [{host_regex, module}, …]
  base.py              # AtsAdapter protocol: matches(url) -> bool; fetch(url) -> dict
  workday.py           # per-ATS adapters
  oracle_hcm.py
  greenhouse.py
  lever.py
  ashby.py
  smartrecruiters.py
  jsonld.py            # universal fallback: parse schema.org/JobPosting
  llm_fallback.py      # existing from_url flow, last resort
```

`from_url.job_from_url` becomes: iterate adapters in priority order, return
first hit. LLM path stays as last-resort catch-all — small firms' careers
pages will always need it.

Additional concerns worth naming, deferred until they bite:

- **Per-host discovery cache.** Workday tenant→site slugs, Greenhouse board
  tokens on customer domains. Cache in SQLite keyed by host; TTL 30 days.
- **Headless browser worker.** Only needed if BambooHR/SuccessFactors coverage
  becomes required. Playwright in a container, called from a background
  queue — never inline in a request. Not needed for Oracle HCM (REST endpoint
  works without a browser).
- **Adapter output validation.** Each adapter should return the same dict
  shape `_to_job_dict` currently returns. A shared `validate_job_dict()`
  helper prevents drift.
- **Failure attribution.** Emit an `extract.failed` event tagged with the ATS
  name so we notice when Workday changes its response shape (they do).

## 8. Order of work

1. Extract the routing layer (`core/jobs/ats/`), moving current LLM flow
   behind it as the fallback. No behavior change yet.
2. Ship Greenhouse and Lever adapters — they're 20 lines each, high hit rate.
3. Ship Workday adapter — the highest-value one; also validates the
   POST-with-body pattern.
4. Ship Oracle HCM adapter — unblocks the concrete URL that started this
   research.
5. Ship Ashby + JSON-LD universal fallback in one pass.
6. Only then evaluate whether iCIMS/SuccessFactors/BambooHR are worth the
   complexity. Data from `extract.failed` events will answer that.

---

Sources: [ResumeGeni ATS Market Share 2026](https://resumegeni.com/research/ats-market-share-2026), [Mordor Intelligence ATS market report](https://www.mordorintelligence.com/industry-reports/applicant-tracking-system-market), [Oracle Fusion HCM REST API](https://docs.oracle.com/en/cloud/saas/human-resources/farws/op-recruitingicejobrequisitions-get.html), [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html), [Lever developer docs](https://hire.lever.co/developer/documentation), [SmartRecruiters Posting API](https://developers.smartrecruiters.com/docs/posting-api), [JobsPipe Workday guide](https://jobspipe.dev/blog/workday-api-guide), [DEV: every major ATS has a public job feed](https://dev.to/agenticemail/every-major-ats-has-a-public-job-feed-here-is-how-to-read-them-all-3k10), [schema.org JobPosting](https://schema.org/JobPosting), [Oracle Taleo deep-linking config](https://docs.oracle.com/en/cloud/saas/talent-acquisition/17.6/otrdc/deep-linking-configuration.html).
