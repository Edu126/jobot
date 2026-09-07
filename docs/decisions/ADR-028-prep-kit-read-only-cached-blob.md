# ADR-028: Prep kit is one read-only cached blob per session (STAR bank + reverse questions); editing is copy-out, not in-app

Date: 2026-09-03
Status: Accepted
Relates to: REQ-023 (Prep slice 1), ADR-026 (prep_sessions), ADR-027 (company
outlook — separate surface), REQ-018/ADR-021 (defense hooks, reused), GOV-005
(enhance ≠ fabricate), ADR-005 (grounded-or-none), ADR-008 (prompt/cache)

## Context

Beyond the company outlook (ADR-027), the slice-1 kit has two AI surfaces from
the designer mockup (2026-09-03): a **Tailored STAR Q&A bank** (behavioral +
defensive-gap answers) and a **Reverse Interviewing** list (questions to ask,
grouped by category, copy-first). Constraints real now: Gemini quota is scarce;
per-user SQLite; the honesty line is non-negotiable (GOV-005, grounded-or-none);
the house pattern is a JSON blob cached on résumé-hash/lang/prompt_version
(`gap_enhancements`). Product calls locked this session: the kit is **read +
copy**, *not* in-app editable; and there is **no user-facing Q&A regenerate**
(non-negotiable #2).

## Decision

One **`prep_kits`** table, PK **(prep_session_id, lang, prompt_version)**,
holding a single `kit_json` blob + `model` + `created_at`. **Read-only cache,
no user-edit layer** — the kit is copy-first (buttons copy into the user's own
prep). Generated lazily on session open, cached thereafter.

`kit_json` shape:
- `star_qa: [{ id, kind, question, answer }]`, `kind ∈
  behavioral | defensive_gap | why_you | situational | culture_fit`. `answer`
  is a discriminated union: `{star: {s,t,a,r}}` for experience-backed questions,
  `{talking_points: [...]}` for `defensive_gap`. Defensive-gap items **reuse the
  REQ-018 defense hooks** when the session is `job_id`-bound (ADR-026); otherwise
  generated from the résumé.
- `reverse_qs: [{ id, category, question }]`, grouped (Culture & Team, Role
  Success / 90-day, Tech & Data…). Copy is client-side; no persisted state.

**Grounding (GOV-005):** every STAR must cite *real* résumé experience; the call
is grounded on the candidate text and gated **grounded-or-none** (ADR-005) — a
STAR that can't ground on a real experience does not render. No fabricated
situations. Optional light `source_ref` per item for traceability.

**No bulk "Refresh Q&A":** the bank is authored once per `prompt_version`;
quality lives in the prompt, not a retry button (non-negotiable #2). The only
sanctioned refresh in Prep is company news (ADR-027 — live data, not distrust).

The Q&A/reverse content is JSON-mode (ADR-008 rule 1) and separate from the
GoogleSearch outlook call. Register the new site(s) in `llm-surface.md`.

## Alternatives considered

- **Normalized per-item rows (`prep_qa`) with state:** rejected — over-
  engineered for a read-only cache; regeneration is atomic on a blob; there is
  no per-item mutable state to justify the machinery.
- **Cache + user-edit layer (like `gap_dismissals`):** rejected for MVP — the
  mockup is copy-first, not editable; an edit layer buys nothing until in-app
  editing exists. Revisit if editing is added (it would key on stable item ids).
- **STAR as free text:** rejected — the S/T/A/R structure is the value
  (scannable, teaches the format) and lets us check each part is grounded.
- **One call for the whole kit incl. outlook:** rejected — outlook needs
  GoogleSearch (ADR-027, no JSON); Q&A/reverse is JSON-mode. Different contracts
  ⇒ separate calls.

## Consequences

- One new table + one/two Gemini call sites (reverse questions may share the
  Q&A call). Must be added to `llm-surface.md` and follow ADR-008.
- Read-only means a résumé change or `prompt_version` bump regenerates the whole
  blob — fine, nothing user-authored is lost (there is nothing user-authored).
- `id`s are stable only within a kit version — acceptable *precisely because*
  there's no cross-version user state to preserve. Read-only + no-regenerate
  compose cleanly; the moment we add **either** editing **or** a regenerate, the
  id-stability problem appears and this ADR is superseded on the storage layer.
- The variable `answer` shape (`star | talking_points`) pushes a small
  discriminated union into the renderer; `kind` drives it. Acceptable.
- STAR quality tracks résumé richness: a thin résumé yields thin STARs or none
  (grounded-or-none). Honest — better empty than fabricated (GOV-005).
