"""Scoring bake-off — 3 competing skill-extraction/coverage approaches on
REAL resumes x REAL JDs, side by side. Diagnostic only (not production).

Question it answers (Eduardo, 2026-08-28): does ESCO-alone fail on tooling,
and does a cheap LLM-assist reinforce it enough to justify the call?

Approaches, layered so the marginal value of each is visible:
  1. local_baseline  — TF-IDF top terms + DOMAIN_HINTS (~ current lite engine)
  2. esco_local      — (1) but each candidate term validated against ESCO's
                       exact label (Jaccard>=.5) OR a known tool → kills the
                       company-name/stopword pollution
  3. llm_hybrid      — Gemini extracts normalized skills+tools from the JD's
                       meat and from the resume; coverage in that space

Run:  python scripts/scoring_bakeoff.py [--no-llm]
Caches ESCO lookups + LLM extractions in data/bakeoff_cache/ so reruns are
cheap and deterministic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core import db
from core.matching.lexical import normalize as _norm
from core.matching.lite_score import _resume_membership
from core.matching.tfidf_match import DOMAIN_HINTS, match as tfidf_match

CACHE = APP_ROOT / "data" / "bakeoff_cache"
CACHE.mkdir(parents=True, exist_ok=True)

_STRONG, _GOOD = 0.60, 0.35


def _bucket(cov: float) -> str:
    return "Strong" if cov >= _STRONG else "Good" if cov >= _GOOD else "Weak"


# ---------- ESCO exact-ish validation (Jaccard over labels) ----------
def _esco_hit(term: str, lang: str) -> bool:
    """True if `term` maps to a real ESCO skill (not a fuzzy garbage hit)."""
    key = CACHE / f"esco_{lang}_{hashlib.md5(term.encode()).hexdigest()}.json"
    if key.exists():
        label = json.loads(key.read_text()).get("label")
    else:
        url = ("https://ec.europa.eu/esco/api/search?text="
               + urllib.parse.quote(term) + f"&language={lang}&type=skill&limit=1")
        label = None
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.loads(r.read())
            res = d.get("_embedded", {}).get("results", [])
            label = res[0]["title"] if res else None
        except Exception:
            label = None
        key.write_text(json.dumps({"label": label}))
    if not label:
        return False
    qt, lt = set(_norm(term).split()), set(_norm(label).split())
    if not qt:
        return False
    jacc = len(qt & lt) / len(qt | lt)
    return jacc >= 0.5 or _norm(term) in _norm(label)


def _is_tool(term: str) -> bool:
    t = _norm(term)
    return any(t == h or t in h or h in t for h in DOMAIN_HINTS)


# ---------- LLM extraction (his "strong, open, analytical" prompt) ----------
_LLM_PROMPT = """You are a rigorous skills analyst. Read the text below and extract, \
with an open and analytical eye, the CONCRETE professional competences and the \
TOOLS/technologies it demonstrates or requires. Normalize to canonical names \
(e.g. "PowerBI"->"power bi", "gestion de proyectos"->"project management" ONLY if \
the text's language is that; keep the text's own language). Infer tools strongly \
implied even if not named as a heading. Ignore company names, boilerplate, soft \
filler. Return STRICT JSON: {{"skills": [..], "tools": [..]}} — short lowercase items.

TEXT ({kind}):
{text}
"""


def _llm_extract(text: str, kind: str, client) -> dict:
    key = CACHE / f"llm_{kind}_{hashlib.md5(text.encode()).hexdigest()}.json"
    if key.exists():
        return json.loads(key.read_text())
    out = client.generate_json(_LLM_PROMPT.format(kind=kind, text=text[:6000]))
    norm = {
        "skills": [_norm(s) for s in (out.get("skills") or []) if s],
        "tools": [_norm(t) for t in (out.get("tools") or []) if t],
    }
    key.write_text(json.dumps(norm))
    return norm


# ---------- the three approaches ----------
def local_baseline(resume: str, jd: str) -> dict:
    m = tfidf_match(resume, jd, top_n_missing=15)
    matched, missing = m["matched_keywords"], m["missing_keywords"]
    total = len(matched) + len(missing)
    cov = len(matched) / total if total else 0.0
    return {"cov": cov, "bucket": _bucket(cov), "matched": matched[:8], "missing": missing[:8]}


def esco_local(resume: str, jd: str, lang: str) -> dict:
    m = tfidf_match(resume, jd, top_n_missing=40)
    # candidate skill terms = everything TF-IDF surfaced (matched + missing)
    cands = list(dict.fromkeys(m["matched_keywords"] + m["missing_keywords"]))
    resume_norm = _norm(resume)
    real, matched, missing = [], [], []
    for c in cands:
        if _is_tool(c) or _esco_hit(c, lang):
            real.append(c)
            (matched if _norm(c) in resume_norm else missing).append(c)
    cov = len(matched) / len(real) if real else 0.0
    return {"cov": cov, "bucket": _bucket(cov), "matched": matched[:8],
            "missing": missing[:8], "n_real": len(real), "n_cands": len(cands)}


def llm_local_hybrid(resume: str, jd: str, client) -> dict:
    """THE HYBRID HEART: LLM extracts the JD's required skills+tools (clean,
    tooling-aware, multilingual), then each is matched against the resume with
    the tolerant LOCAL matcher (stems/substring) — NOT a 2nd independent LLM
    extraction. Reuses the cached JD extraction, so no extra LLM call."""
    jd_x = _llm_extract(jd, "job description", client)
    reqs = list(dict.fromkeys(jd_x["skills"] + jd_x["tools"]))
    in_resume = _resume_membership(_norm(resume))
    matched = [t for t in reqs if in_resume(_norm(t))]
    missing = [t for t in reqs if not in_resume(_norm(t))]
    cov = len(matched) / len(reqs) if reqs else 0.0
    return {"cov": cov, "bucket": _bucket(cov), "matched": matched[:8],
            "missing": missing[:8], "n_reqs": len(reqs)}


_JUDGE_PROMPT = """You are a fair, analytical hiring analyst. Below is a list of \
REQUIREMENTS a job asks for, and a candidate's RESUME. For EACH requirement decide, \
with an open mind, whether the resume genuinely EVIDENCES it — judging by meaning, \
not exact words. Cross-language counts (a Spanish resume can evidence an English \
requirement, e.g. "selección de personal" evidences "recruitment"; "gestión de \
proyectos" evidences "project management"). Paraphrase and transferable evidence \
count; do NOT credit a requirement the resume gives no real basis for. Return STRICT \
JSON: {{"matched": [..requirements evidenced..], "missing": [..not evidenced..]}} — \
echo each requirement string exactly as given.

REQUIREMENTS: {reqs}

RESUME:
{resume}
"""


def llm_judge_match(resume: str, jd: str, client) -> dict:
    """APPROACH B: LLM extracts JD requirements (cached), then the LLM JUDGES which
    the resume evidences — semantic + cross-language. One call per (resume, JD) pair,
    cached by both hashes."""
    jd_x = _llm_extract(jd, "job description", client)
    reqs = list(dict.fromkeys(jd_x["skills"] + jd_x["tools"]))
    if not reqs:
        return {"cov": 0.0, "bucket": "Weak", "matched": [], "missing": [], "n_reqs": 0}
    key = CACHE / f"judge_{hashlib.md5((resume + '|' + '|'.join(reqs)).encode()).hexdigest()}.json"
    if key.exists():
        out = json.loads(key.read_text())
    else:
        out = client.generate_json(_JUDGE_PROMPT.format(reqs=json.dumps(reqs), resume=resume[:6000]))
        out = {"matched": out.get("matched") or [], "missing": out.get("missing") or []}
        key.write_text(json.dumps(out))
    matched = [r for r in reqs if r in set(out["matched"])]
    missing = [r for r in reqs if r not in set(out["matched"])]
    cov = len(matched) / len(reqs) if reqs else 0.0
    return {"cov": cov, "bucket": _bucket(cov), "matched": matched[:8],
            "missing": missing[:8], "n_reqs": len(reqs)}


def llm_hybrid(resume: str, jd: str, client) -> dict:
    jd_x = _llm_extract(jd, "job description", client)
    r_x = _llm_extract(resume, "resume", client)
    jd_set = set(jd_x["skills"]) | set(jd_x["tools"])
    r_set = set(r_x["skills"]) | set(r_x["tools"])
    matched = sorted(jd_set & r_set)
    missing = sorted(jd_set - r_set)
    cov = len(matched) / len(jd_set) if jd_set else 0.0
    return {"cov": cov, "bucket": _bucket(cov), "matched": matched[:8],
            "missing": missing[:8], "jd_tools": jd_x["tools"][:8]}


# ---------- fixtures ----------
_FIX = APP_ROOT / "data" / "bakeoff_fixtures"


def _resume_text(source: str) -> str:
    """source = 'db:<id>' (parsed resume) or a fixture filename under data/bakeoff_fixtures/."""
    if source.startswith("db:"):
        r = db.get_resume(int(source[3:]))
        return (r.get("parsed") or {}).get("raw_text", "") if r else ""
    p = _FIX / source
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _load_jd(cache_file: str, title_contains: str) -> dict | None:
    d = json.loads((APP_ROOT / "data" / "jobs_cache" / cache_file).read_text())
    for j in d.get("jobs") or []:
        if title_contains.lower() in (j.get("title") or "").lower():
            return j
    return None


# (source, label, domain, [ (cache_file, title_contains, jd_label) ... ])  — each
# profile gets an ON-DOMAIN JD + a contrast, so we see the engine differentiate.
SEED = [
    ("db:14", "Eduardo", "BI / data analytics", [
        ("3107f0c8d5eb7bee.json", "Data Analyst", "Data EN (on-domain)"),
        ("fba634c53a2ed9c7.json", "Construction Project Coordinator", "AEC EN (off-domain)"),
    ]),
    ("db:3", "Mehran", "AEC / construction", [
        ("fba634c53a2ed9c7.json", "Construction Project Coordinator", "AEC EN (on-domain)"),
        ("6a72791cbb37c421.json", "Technologue en architecture", "AEC FR"),
    ]),
    ("andrea_sales.txt", "Andrea", "Sales / comercial (ES)", [
        ("01791d02c9e579c6.json", "Analista Comercial", "Sales ES (on-domain)"),
        ("01791d02c9e579c6.json", "Account Manager", "Sales EN"),
    ]),
    ("sara_hr.txt", "Sara", "HR / people (ES/EN)", [
        ("9dc7699d100f92cc.json", "People & Culture Coordinator", "HR EN (on-domain)"),
        ("01791d02c9e579c6.json", "Analista Comercial", "Sales ES (adjacent)"),
    ]),
    ("melisa_grc.txt", "Melisa", "GRC / compliance / cyber (EN)", [
        ("6a72791cbb37c421.json", "Cloud Security Architect", "Security EN (on-domain)"),
        ("3107f0c8d5eb7bee.json", "Data Analyst", "Data EN (adjacent)"),
    ]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip approach 3")
    ap.add_argument("--hybrid", action="store_true",
                    help="run ONLY approach 4 (LLM-JD x local matcher), reusing cached extractions")
    args = ap.parse_args()

    client = None
    if not args.no_llm:
        from core.llm.gemini import GeminiClient, resolve_api_key
        client = GeminiClient(api_key=resolve_api_key())

    if args.hybrid:
        for source, rname, rdom, jds in SEED:
            resume = _resume_text(source)
            if not resume:
                continue
            print(f"\n{rname} — {rdom}", flush=True)
            for cf, tc, jlabel in jds:
                j = _load_jd(cf, tc)
                if not j:
                    continue
                jd = j.get("description") or ""
                a = llm_local_hybrid(resume, jd, client)
                b = llm_judge_match(resume, jd, client)
                print(f"  {jlabel}", flush=True)
                print(f"    A local-match  {a['bucket']:6} cov={a['cov']:.2f} ({len(a['matched'])}/{a['n_reqs']})", flush=True)
                print(f"    B llm-judge    {b['bucket']:6} cov={b['cov']:.2f} ({len(b['matched'])}/{b['n_reqs']})", flush=True)
                print(f"      B matched={b['matched'][:6]}", flush=True)
                print(f"      B gaps   ={b['missing'][:6]}", flush=True)
        return

    for source, rname, rdom, jds in SEED:
        resume = _resume_text(source)
        if not resume:
            print(f"!! no resume text for {rname} ({source})", flush=True)
            continue
        print("\n" + "=" * 78, flush=True)
        print(f"RESUME: {rname} — {rdom}", flush=True)
        print("=" * 78, flush=True)
        for cf, tc, jlabel in jds:
            j = _load_jd(cf, tc)
            if not j:
                print(f"  (JD not found: {tc})", flush=True)
                continue
            jd = j.get("description") or ""
            lang = j.get("detected_language") or "en"
            esco_lang = lang if lang in ("en", "es", "fr") else "en"
            print(f"\n  JD: {j.get('title')[:55]}  [{jlabel}] detected={lang}", flush=True)
            b = local_baseline(resume, jd)
            print(f"    1 local     {b['bucket']:6} cov={b['cov']:.2f}  gaps={b['missing'][:5]}", flush=True)
            e = esco_local(resume, jd, esco_lang)
            print(f"    2 esco+tool {e['bucket']:6} cov={e['cov']:.2f}  "
                  f"({e['n_real']}/{e['n_cands']} cands real)  gaps={e['missing'][:5]}", flush=True)
            if client:
                try:
                    l = llm_hybrid(resume, jd, client)
                    print(f"    3 llm       {l['bucket']:6} cov={l['cov']:.2f}  matched={l['matched'][:5]}", flush=True)
                    print(f"                gaps={l['missing'][:6]}", flush=True)
                    print(f"                jd_tools_seen={l['jd_tools']}", flush=True)
                except Exception as ex:
                    print(f"    3 llm       ERROR {ex}", flush=True)


if __name__ == "__main__":
    main()
