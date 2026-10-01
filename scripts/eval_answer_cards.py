"""Answer-card quality eval (ADR-058, Phase 4) — before/after, offline.

Grades every cached Get Ready toolkit of one interview (each prompt version =
one arm: v2 prose answers vs v3 skeletons) with the interviewer judge
(core/prep/answer_judge.py) and prints a per-version table:

  answered  = % of cards that answer the question asked
  spec      = mean specificity (1–5)
  filler    = cards with filler phrases (judge) + code detector hits (v3 only)
  invented  = cards with claims not in résumé + clarifications
  hints     = v3 cards that carry a [[hint: …]] slot (honest gaps)

Targets (ADR-058): answered 100%, spec ≥ 4, filler 0, invented 0.

Runs against a DB COPY (never the live -edu DB). Self-judging caveat: Gemini
writes and grades — `--export-dir` dumps the cards as JSON so an independent
model can grade them blind.

    .venv/bin/python scripts/eval_answer_cards.py --db data/edu_copy.sqlite --interview 3
    .venv/bin/python scripts/eval_answer_cards.py --db data/edu_copy.sqlite --interview 3 --export-dir data/cards_judge
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.gemini import GeminiClient, resolve_api_key  # noqa: E402
from core.prep import answer_judge as AJ  # noqa: E402
from core.prep import toolkit as T  # noqa: E402


def _load(db: Path, interview_id: int, since: str = "") -> tuple[list[tuple[str, dict]], dict[str, str], str]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    arms = [(r["prompt_version"], json.loads(r["artifact_json"])) for r in conn.execute(
        "SELECT prompt_version, artifact_json FROM prep_artifacts WHERE interview_id=? AND kind='toolkit' "
        "AND created_at >= ? ORDER BY created_at", (interview_id, since))]
    frow = conn.execute(
        "SELECT artifact_json FROM prep_artifacts WHERE interview_id=? AND kind='facts' ORDER BY created_at DESC LIMIT 1",
        (interview_id,)).fetchone()
    facts = json.loads(frow["artifact_json"]) if frow else {}
    facts = {k: v for k, v in facts.items() if not str(k).startswith("__")} if isinstance(facts, dict) else {}
    iv = conn.execute("SELECT resume_id FROM interviews WHERE id=?", (interview_id,)).fetchone()
    resume = ""
    if iv and iv["resume_id"]:
        r = conn.execute("SELECT parsed_json FROM resumes WHERE id=?", (iv["resume_id"],)).fetchone()
        if r:  # same source the app uses: parsed["raw_text"]
            resume = (json.loads(r["parsed_json"] or "{}").get("raw_text") or "").strip()
    conn.close()
    return arms, (facts if isinstance(facts, dict) else {}), resume


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--interview", required=True, type=int)
    ap.add_argument("--export-dir", type=Path)
    ap.add_argument("--resume-file", type=Path, help="résumé text if the DB copy lacks it")
    ap.add_argument("--since", default="", help="only toolkits created at/after this ISO time")
    a = ap.parse_args()

    arms, facts, resume = _load(a.db, a.interview, a.since)
    if a.resume_file:
        resume = a.resume_file.read_text(encoding="utf-8")
    if not arms:
        print("no cached toolkit for that interview")
        return 1
    client = GeminiClient(api_key=resolve_api_key())

    print(f"{'version':<34} {'cards':>5} {'answered':>9} {'spec':>5} {'filler':>7} {'invented':>9} {'hints':>6}")
    for version, art in arms:
        cards = [q for q in (art.get("questions") or []) if isinstance(q, dict)]
        rows = []
        for q in cards:
            text = AJ.card_text(q)
            v = AJ.judge_card(q.get("text", ""), text, resume, facts, client)
            rows.append((q, text, v))
        graded = [r for r in rows if r[2]]
        n = len(graded) or 1
        answered = sum(1 for _, _, v in graded if v.answers_the_question) / n * 100
        spec = sum(v.specificity for _, _, v in graded) / n
        filler = sum(1 for q, t, v in graded if v.filler_phrases or T.find_filler(t))
        invented = sum(1 for _, _, v in graded if v.invented_facts)
        hints = sum(1 for q, _, _ in rows if T.HINT_OPEN in json.dumps(q.get("frame") or []))
        print(f"{version[:34]:<34} {len(cards):>5} {answered:>8.0f}% {spec:>5.1f} {filler:>7} {invented:>9} {hints:>6}")
        for q, t, v in graded:
            if not v.answers_the_question or v.specificity <= 2 or v.invented_facts:
                print(f"    ✗ {q.get('text', '')[:70]} — {v.one_liner[:90]}")
        if a.export_dir:
            a.export_dir.mkdir(parents=True, exist_ok=True)
            out = [{"question": q.get("text"), "type": q.get("type"), "answer": t,
                    "gemini_verdict": v.to_dict() if v else None} for q, t, v in rows]
            (a.export_dir / f"iv{a.interview}_{version.split(':')[0]}.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\ntargets: answered 100% · spec ≥ 4 · filler 0 · invented 0   (Gemini self-judged — see --export-dir)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
