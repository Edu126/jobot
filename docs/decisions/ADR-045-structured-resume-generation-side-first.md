# ADR-045: Adopt structured resume data — on the generation side first

Date: 2026-09-15
Status: Proposed (phased per REQ-039; not built)
Relates to: REQ-039, EXP-001 (single score is trustworthy), ADR-005 (fidelity in
the contract layer), the fit_story module (core/matching/fit_story.py)

## Context

The resume flows through the pipeline as a flat `sections → list-of-strings`
blob (parser, `rewrite.py`, `writer.py` all speak it). This blocks two wanted
things at once: **multiple visual templates** (a layout engine can't re-arrange
entries it can't see as `{company, role, dates, highlights[]}`) and a
**breakdown score** (can't score skills vs experience vs seniority over flat
text). Both are the same missing thing: structure.

Two costs shape the decision. (1) The jsonresume.org schema is a useful
reference but rigid and dated (2014) — not a straitjacket. (2) Structured
*parsing* of uploaded docx/pdf is an error-prone extraction problem with real
fidelity risk (the ADR-005 section-collapse failure mode).

## Decision

Adopt a **structured resume data model** (JSON-Resume *pattern*, our own schema),
introduced on the **GENERATION side first**: the tailor LLM — which already
rewrites the resume — emits structured `work[]/highlights[]`, a schema change on
an existing call, NOT a new parser. Uploaded resumes stay flat-parsed in v1.
This structured tailored object is the single source multiple templates render
from AND the substrate the breakdown score is computed over. Each phase
(REQ-039) is validated with the adversarial harness before the next. The single
0-100 stays the accuracy signal (EXP-001); the breakdown is transparency.

## Alternatives considered

- **Adopt jsonresume.org literally** — rejected: rigid/dated, missing our ATS +
  tailoring needs.
- **Structured PARSER first** — rejected for v1: high fidelity risk, big lift;
  deferred to REQ-039 Phase 3, gated on Phases 0-2 paying off.
- **Status quo (flat sections)** — rejected: permanently blocks templates and
  the breakdown; forces every resume to look identical.
