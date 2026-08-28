# RESEARCH-market-thesis — is the jobot thesis grounded in evidence?

Date: 2026-08-27
Status: **Reviewed** (2026-08-27, iterations 1+2). Decisions applied — see
REQ-016, ADR-016, ADR-017, GOV-004, product/vision.md reframe.
Feeds: product/vision.md, milestones.md, REQ-015, GOV-003
Mode: deep (3 pillars + 1 founder-led sourcing pillar)

Consolidated from 4 parallel Sonnet sub-agents (see RESEARCH-PLAN-market-thesis.md).
Sources marked ✓ verified (OpenAlex/Crossref) or ⚠ unverified (industry/vendor).

## TL;DR

1. **The heart is confirmed by hard science.** Job search is a demand-heavy,
   resource-poor activity; **job-search self-efficacy (JSSE)** is the central
   psychological lever, and it erodes under friction and rejection in a negative
   loop. Jobot = the resource injection that protects it. *All ✓ peer-reviewed.*
2. **"Beat the ATS" is a myth — and a liability.** The "75% auto-rejected" stat
   is fabricated; 92% of recruiters manually review; the real hard gate is
   **knockout/eligibility questions**, not score thresholds. Reframe required.
3. **Tailoring commoditizes — now with data.** A ✓-verified 2025 field experiment
   shows AI cover letters raised callbacks *but* the signal value of text fell
   **51%** as employers shifted weight to **work history / portfolio**. Substance
   > prose.
4. **Auto-apply is a ToS landmine (confirmed).** Platforms ban automated
   submission, not AI-assisted drafting the user reviews. Jobot must stay a
   drafting assistant, never an auto-submitter.
5. **Digital tools as a JSSE moderator are almost unstudied** → academic gap =
   moat, and a possible original-data angle for jobot.

## Findings by pillar

### Pillar 1 — Psychology of job search (backbone: ✓ verified)
- JSSE predicts search intensity and employment outcomes (meta-analytic ρ=.27,
  k=90; confirmed across 378 samples / N=165,933). ✓
- Structured interventions (skill + self-efficacy + goal-setting) → **2.67×**
  reemployment odds. ✓
- Unemployment causes measurable psychological harm (d=−0.51 well-being). ✓
- Expressive/emotional offloading improves outcomes. ✓
- Digital/AI tools as JSSE moderators: **almost unstudied** (Zheng 2025). ✓
- Tension: higher JSSE raises *volume*, but breadth without targeting lowers
  offer rate → validates "apply better, not just more."

### Pillar 2 — ATS / automated screening (mixed: academic ✓, industry ⚠)
- "75% rejected by ATS" is fabricated (traced to defunct Preptel, 2013); 92% of
  recruiters manually review. Parsing *deprioritizes*, it doesn't auto-reject. ⚠
- Real hard gate = **knockout questions** (eligibility: work auth, license,
  location, years) — filters ~50%. ⚠ (consistent across vendor docs)
- Format genuinely breaks parsers: text PDF ~75% parse vs. designed ~45%;
  multi-column/tables/headers fail. ⚠+arXiv ✓
- ATS shifting to **semantic/LLM matching** (Resume2Vec ✓, IIUM ✓, LLM-ATS ✓)
  → jobot's LLM scoring is aligned with the tech direction (tailwind).
- Convergence: on modern semantic stacks, real-fit ≈ ATS-fit; on legacy keyword
  stacks the gap remains, and jobot can't know which the employer runs.

### Pillar 3 — AI tailoring in the age of AI screening (key finding ✓; stats ⚠)
- **Cui, Dias & Ye 2025** (✓ arXiv 2509.25054): AI cover letters ↑ callbacks,
  but text-alignment signal ↓ **51%**; employers shifted to work history. Editing
  effort still predicts success → **"AI-structured, user-voiced."**
- Platforms ban auto-apply bots / "human-impossible velocity" (100+/hr), NOT
  AI-assisted content the user reviews. ⚠ (ToS interpretation)
- Personalized AI accepted by ~63% of HMs; unpersonalized rejected by ~62%. ⚠
- Fabrication is the hard line — passes screening, fails reference/background;
  brand risk for jobot by association.
- No ✓ academic evidence for the "35–300% ATS keyword lift" marketing claims. ⚠

### Pillar 4 — Founder-agent systems (founder-led sourcing, no conclusions)
12 real systems inventoried (CoFounder.im, Cofounder.co, BMAD-METHOD,
ivfarias/ceo, council-ai, Seven Advisors, MIT Sloan "Personal Board of
Directors", etc.). Two structural patterns: **sequential pipeline** vs.
**parallel council + synthesis**; **router + specialist** dominant. Open gaps
for Eduardo to probe: persistent "god-mode strategist" with longitudinal
context; a "real user / customer voice" role; surfaced disagreement vs.
forced synthesis. (Full inventory in the pillar-4 brief.)

## Tensions / open questions
- Where does the tailoring arms race settle — new floor, or full homogenization?
- Real-fit vs. ATS-fit converge only on modern stacks; jobot can't detect which.
- "Editing time predicts success" is correlational (may proxy motivation/fit).
- Industry stats (volume, %, ghost jobs) are ⚠ vendor-sourced — directional only.
- Eligibility/knockout is the true binary but lives at the application layer,
  partly outside jobot's current control.

## Implications for jobot (the bridge — prioritized)

| # | Finding | So what for jobot | Action hook |
|---|---|---|---|
| 1 | "Beat the ATS" is a myth + legal/credibility risk | Reframe from "beat the ATS" to **"be eligible · be seen · be ranked · be real."** | **Update product/vision.md** + GOV marketing-copy review |
| 2 | Knockout/eligibility is the true binary gate | Score **eligibility (hard requirements) BEFORE fit**; a 90% fit on an ineligible role is noise | **REQ-015**: eligibility pre-filter layer before fit score |
| 3 | Auto-apply banned; AI-assist allowed | Jobot drafts, user submits **each** application; never auto-submit | **New ADR**: no-auto-submit architecture constraint (ties GOV-003, Phase 4) |
| 4 | Text signal decays 51%; work history rises | Push **quantified achievements + portfolio**, not just prose tailoring | Backlog: "achievement mining" flow |
| 5 | Fabrication is the hard line | All factual claims trace to user input; min-specificity check before export; track edit depth | **REQ**: generation guardrail + specificity gate |
| 6 | Format breaks parsers regardless of content | Lock resume output to ATS-safe (single-column, text, no tables/headers) | REQ/ADR: ATS-safe template as hard constraint |
| 7 | JSSE erodes under friction; progress sustains it | Minimize steps per application; show progress/momentum signals | REQ (fewer steps) + backlog (momentum widget) |
| 8 | Digital tools as JSSE moderator unstudied | Instrument JSSE proxies (dropout, re-open rate); possible original-data moat | Feeds Phase-0 analytics + a research angle |
| 9 | Ghost jobs + thin oversight; quality>quantity | Prioritize applications with employer engagement signals | Backlog: response-signal prioritization (Phase 4 seed) |

## Decisions to make here (with Eduardo)
- **A.** Accept the "beat the ATS" → "eligible/seen/ranked/real" reframe into
  product/vision.md? (my recommendation: yes — it's a myth + a liability)
- **B.** Fold eligibility pre-filter (#2) into REQ-015 scoring now, or keep REQ-015
  as-is and add a REQ-016?
- **C.** Cut the no-auto-submit ADR (#3) now — does it constrain the Phase-4
  agent vision, or just make it "agent drafts, human submits"?

## Sources
Verified academic backbone (✓): Kanfer 2001; McKee-Ryan 2005; Wanberg 2012;
Liu-Huang-Wang 2014; Moynihan 2003; van Hooft 2021; Zheng 2025; Resume2Vec 2025;
IIUM IJPCC 2026; IJSSIC 2024; Cui-Dias-Ye 2025 (arXiv 2509.25054). Industry/vendor
(⚠): LinkedIn volume, HR.com survey, Jobscan, knockout-question vendor docs,
ghost-job reports. Full source lists in the four pillar briefs.

---

# Iteration 2 — the ranking gate + the funnel + the career big-picture

Added 2026-08-27. Iteration 1 left the ATS pillar lukewarm: it debunked
auto-rejection but buried the real mechanism. Four more Sonnet agents
(ranking algorithms · how products score/surface · funnel reverse-engineering
· career-planning psychology) sharpen it.

## The sharpened core: auto-reject is the myth, RANKING is the gate

Recruiters don't read applications — they read a list **already scored and
ranked by AI, top-down, and rarely reach the fold**. Volume (~11k apps/min)
and thin oversight (~29% full human review) make the AI score *more*
determinative, not less. You don't compete with 200 applicants; you compete
with the ~12 the ranker surfaces.

**How the ranker works (Pillar A, ✓ verified):**
- Two-stage: fast **bi-encoder retrieval** (thousands→~100) then
  **cross-encoder / LLM re-ranker** produces the human-read shortlist
  (ConFit v1/v2/v3 ✓, CareerBERT ✓, Resume2Vec ✓).
- **Skills coverage is the dominant feature; job-title proximity second**
  (exact target title ≈ 10.6× interview lift).
- **Scores are NOT calibrated** across candidates/jobs — a raw "85%" is not
  comparable. Show fit as **percentile / label bucket**, not a raw %.
- ESCO/O*NET normalisation closes the synonym gap (React ↔ ReactJS).
- Listwise scoring (compare 3–5 JDs at once) beats pointwise; collecting
  user outcome signals enables later fine-tuning; TalentCLEF is a free
  public benchmark.

**How products surface it (Pillar B, mixed ✓/⚠):**
- Eightfold (1–5), LinkedIn (High/Med/Low + "Top Applicant" = top 50%),
  HiredScore (traffic-light) sort before any human sees candidates.
- **Position bias:** ~65% of list-readers click the first relevant item;
  LinkedIn Hiring Assistant pilots reviewed **62% fewer profiles**.
- Score = skill keywords + title proximity + enriched public data; vendors
  are **opaque** about weights.
- **Documented bias + legal heat:** Wilson & Caliskan AIES 2024 ✓ — LLM
  resume rankers preferred white-associated names 85.1%; Mobley v. Workday
  collective action certified (2025) over proxies like **career gaps**;
  "Null Compliance" FAccT 2024 ✓ — only 18/391 employers posted audits.
- **The trust gap:** only **26% of candidates** trust AI scoring vs **70%
  of hiring managers** (Gartner 2025 ✓). Transparency = a real wedge.

## The funnel (Pillar C) — where effort converts

- ~180 applications per hire (0.6%); the biggest drop is **pre-human** (~3%
  reach an interview).
- Channel yield: **referral ≈ 10× cold**; recruiter-sourced ≈ 8×; targeted
  (≥75% match) ≈ 3–3.5× untargeted. (All ⚠ vendor benchmarks — directional.)
- ~20% of postings are **ghost jobs**; spray-and-pray (>80 apps) has *worse*
  outcomes than focused (21–80).
- Leverage order: **referral activation > skill/title alignment > ghost-job
  avoidance > interview prep.** Lowest yield: mass cold-apply, generic
  resumes, ghost jobs.

## The career big-picture (Pillar D, ✓ verified) — the continuous layer

- Careers are **self-authored narratives** (Savickas, Life Designing ✓) →
  the "career persona" IS a career story that evolves, not a title list.
- **Protean orientation** (values-driven, self-directed) predicts career
  *satisfaction* → users stay because the tool reflects *them* (Wiernik &
  Kostal 2019 ✓). The retention-paradox fix has academic legs.
- **7 career-self-management behaviors** (Wilhelm 2023 ✓) map 1:1 to a
  Phase-3 feature taxonomy (self-exploration, goal-setting, human-capital
  dev, networking, mobility…).
- **Planned Happenstance** (Krumboltz 2009 ✓) grounds "adjacent roles" /
  serendipity discovery as real, not gimmick.
- **Dosage matters** — periodic check-ins beat one-shot prompts → the
  continuous loop is the theoretically-supported design.

## Updated implications (iteration 2 — highest leverage first)

| # | Finding | So what for jobot | Action hook |
|---|---|---|---|
| R1 | Ranking is the gate; recruiters read top ~5–10 | Jobot's job is the top slot, not "apply". Score must be **rank-aware** | REQ-015: fit as **percentile/bucket**, not raw % |
| R2 | Skills coverage + exact title dominate | Gap output must split **"have skill, wrong word"** vs **"genuinely lack"**, in the JD's terms | REQ-015: language-precise gap engine |
| R3 | Scores uncalibrated (raw % meaningless) | Bucketed labels (Strong/Good/Weak), never comparable raw numbers | ADR (follows ADR-015): bucketed fit display |
| R4 | 26% candidate trust; industry is black-box | **Transparency is the wedge** — show top-3 reasons in plain language | REQ-015 UI + vision non-negotiable #1 |
| R5 | Referral ≈ 10× cold; 70–85% via network | "Who do you know there?" — map mutual connections per job, draft warm intro | Milestones Phase-4 seed → consider pulling earlier |
| R6 | 20% ghost jobs; effort sink | Flag hiring-signal (post age, activity) before the user applies | Backlog: ghost-job / hiring-signal score |
| R7 | Bias vs names / non-English / career gaps | Never penalize career gaps; flag when our estimate may understate for non-English profiles | GOV: bias non-penalization + language-risk note |
| R8 | Careers = narrative; protean → retention | Persona is a **living career story**; values elicitation; renegotiation at transitions | vision.md Phase 3 + REQ-013 onboarding tie-in |
| R9 | 7 CSM behaviors; dosage matters | Structure Phase-3 features on the CSM taxonomy; periodic check-in cadence | Milestones Phase 3 structure |

## Decisions to converge (with Eduardo) — parked + new

- **A** (parked): reframe "beat the ATS" → **"be seen · be ranked · be real"**
  in product/vision.md. *Now strongly confirmed.*
- **B** (parked): fold eligibility pre-filter + the R1–R3 scoring redesign
  into REQ-015, or open REQ-016 for scoring v2?
- **C** (parked): cut the no-auto-submit ADR (reinforced by Mobley legal heat)?
- **D** (new): fit-score display as percentile/bucket — ADR now?
- **E** (new): pull the referral/network lever (R5) forward from Phase 4?
- **F** (new): transparency scoring UI (R4) + GOV bias additions (R7) —
  these are our honesty differentiator; commit now?
