"""Smoke test: run TF-IDF and Gemini semantic scoring side-by-side on
cached jobs, print a comparison table.

Usage:
    cd jobot-app
    python smoke_semantic_score.py [--limit N] [--cache-file FILE]

Requires:
    - GOOGLE_API_KEY (or GEMINI_API_KEY) in env or .env
    - At least one resume in the SQLite DB (upload via Streamlit first)
    - At least one cached search in data/jobs_cache/*.json

Purpose: validate that semantic scoring produces sensible, differentiated
scores before we commit to wiring it into the UI. Look for:
    - Poor-fit jobs (wrong domain) actually get low scores
    - Real matches get 60+ with reasoning that cites the resume
    - Reasoning is one sentence, not generic
    - matched/gaps are concrete tools, not soft skills
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `from core...` when run directly
APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core import db
from core.llm.gemini import DEFAULT_MODEL, GeminiClient, resolve_api_key
from core.matching.semantic_score import score_jobs
from core.matching.tfidf_match import match as tfidf_match


CACHE_DIR = APP_ROOT / "data" / "jobs_cache"


def _pick_cache_file(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = CACHE_DIR / p
        if not p.exists():
            raise SystemExit(f"Cache file not found: {p}")
        return p
    files = sorted(CACHE_DIR.glob("*.json"))
    if not files:
        raise SystemExit(
            f"No cached searches in {CACHE_DIR}. Run a search in Streamlit first."
        )
    return files[0]


def _load_jobs(cache_file: Path, limit: int) -> tuple[list[dict], str]:
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    jobs = payload.get("jobs") or []
    label = payload.get("params_label") or cache_file.stem
    return jobs[:limit], label


def _colorize_score(score: int) -> str:
    if score >= 65:
        return f"\033[92m{score:3d}\033[0m"   # green
    if score >= 40:
        return f"\033[93m{score:3d}\033[0m"   # yellow
    return f"\033[91m{score:3d}\033[0m"       # red


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8,
                    help="How many jobs to score (default 8)")
    ap.add_argument("--cache-file", type=str, default=None,
                    help="Which cache file to load (default: first found)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore SQLite score cache — rescore everything fresh")
    args = ap.parse_args()

    api_key = resolve_api_key()
    if not api_key:
        print("❌ No GOOGLE_API_KEY / GEMINI_API_KEY in env or .env.")
        return 2

    db.init_db()
    resume = db.get_current_resume()
    if not resume:
        print("❌ No resume in DB. Upload one via Streamlit first.")
        return 2

    resume_id = int(resume["id"])
    resume_text = resume["parsed"].get("raw_text", "")
    if not resume_text.strip():
        print("❌ Current resume has empty raw_text. Re-upload the file.")
        return 2

    cache_file = _pick_cache_file(args.cache_file)
    jobs, label = _load_jobs(cache_file, args.limit)
    if not jobs:
        print(f"❌ No jobs in cache file {cache_file.name}.")
        return 2

    print(f"📄 Resume:   #{resume_id} — {resume['filename']}")
    print(f"📁 Search:   {label}  ({cache_file.name})")
    print(f"🔢 Scoring:  {len(jobs)} jobs  (batch=6, model={DEFAULT_MODEL})")
    print()

    # Upsert jobs so FK to job_scores is satisfied
    db.upsert_jobs(jobs)

    # TF-IDF (v1 signal) — cheap, no network
    tfidf_scores: dict[str, int] = {}
    for j in jobs:
        r = tfidf_match(resume_text, j.get("description") or "")
        tfidf_scores[j["id"]] = int(r["similarity_score"])

    # Semantic (v2 signal) — batched Gemini call
    print("⏳ Calling Gemini (batched)…")
    client = GeminiClient(api_key=api_key)
    semantic = score_jobs(
        resume_id=resume_id,
        resume_text=resume_text,
        jobs=jobs,
        client=client,
        use_cache=not args.no_cache,
    )
    print(f"✅ Got {len(semantic)}/{len(jobs)} semantic scores.\n")

    # ---- comparison table ----
    header = f"{'TFIDF':>5}  {'AI':>3}  {'VERDICT':<11}  {'TITLE':<40}  {'COMPANY':<28}"
    print(header)
    print("-" * len(header))

    # Sort by AI score desc so best matches surface first
    def sort_key(j: dict) -> int:
        r = semantic.get(j["id"])
        return -(r.score if r else -1)

    for j in sorted(jobs, key=sort_key):
        r = semantic.get(j["id"])
        tfidf = tfidf_scores.get(j["id"], 0)
        if r is None:
            print(f"{tfidf:>5}  {'---':>3}  {'(skipped)':<11}  "
                  f"{_truncate(j['title'], 40):<40}  {_truncate(j['company'], 28):<28}")
            continue
        print(f"{tfidf:>5}  {_colorize_score(r.score)}  {r.verdict:<11}  "
              f"{_truncate(j['title'], 40):<40}  {_truncate(j['company'], 28):<28}")

    # ---- detail for top 3 ----
    print("\n" + "=" * 80)
    print("TOP 3 — reasoning + matched/gaps")
    print("=" * 80)
    top = sorted(
        [j for j in jobs if j["id"] in semantic],
        key=lambda j: -semantic[j["id"]].score,
    )[:3]
    for j in top:
        r = semantic[j["id"]]
        print(f"\n[{r.score}/100 · {r.verdict}]  {j['title']} — {j['company']}")
        print(f"  Reasoning: {r.reasoning}")
        print(f"  Matched:   {', '.join(r.matched) or '—'}")
        print(f"  Gaps:      {', '.join(r.gaps) or '—'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
