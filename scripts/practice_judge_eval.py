"""Practice-judge leniency eval (next-work #8, REQ-042 weak spot).

Question: how often does the session-score judge band a WEAK answer as
"solid" or "strong"? Runs the real voice-transcript judge
(`practice.session_debrief_from_transcript`, same rubric as the audio path)
over tests/fixtures/practice_judge_set.json — one question + one answer per
item — N times each, because the score drifts even at temperature 0.

    .venv/bin/python scripts/practice_judge_eval.py              # 3 runs each
    .venv/bin/python scripts/practice_judge_eval.py --runs 1 --only vague_result

Costs one Gemini call per item per run (15 items × 3 = 45 small calls).
Reports: false-solid rate (junk runs banded solid/strong), control pass rate
(controls reaching their min band), and per item: bands per run, the checks
the model ticked, and drift.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm.gemini import GeminiClient, resolve_api_key  # noqa: E402
from core.prep import practice as PR  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "practice_judge_set.json"
RANK = {"needs_work": 0, "solid": 1, "strong": 2}


def judge_once(item: dict, comp: dict, client: GeminiClient) -> dict:
    """One judge call → {band, points, checks, verified} for the item's competency."""
    turns = [{"role": "coach", "text": item["question"]}, {"role": "you", "text": item["answer"]}]
    questions = [{"id": "q1", "text": item["question"], "competency_id": comp["id"]}]
    d = PR.session_debrief_from_transcript(turns, questions, [comp], client, lang="en")
    ev = next((e for e in (d.competency_evidence if d else []) if e.get("competency_id") == comp["id"]), None)
    if not ev:
        return {"band": "error", "points": None, "checks": {}, "verified": False}
    band = next((b["band"] for b in d.competency_bands if b.get("competency_id") == comp["id"]), "needs_work")
    return {"band": band, "points": ev.get("points"), "checks": ev.get("checks") or {},
            "verified": bool(ev.get("verified"))}


def passed(item: dict, band: str) -> bool:
    if band == "error":
        return False
    if item["kind"] == "junk":
        return band == "needs_work"
    return RANK[band] >= RANK[item["expect"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", nargs="*", help="item ids to run")
    ap.add_argument("--out", help="also write the report (markdown) here")
    args = ap.parse_args()

    data = json.loads(FIXTURE.read_text())
    items = [i for i in data["items"] if not args.only or i["id"] in args.only]
    client = GeminiClient(api_key=resolve_api_key())

    rows, junk_runs, junk_lenient, ctrl_runs, ctrl_ok = [], 0, 0, 0, 0
    for item in items:
        comp = data["competencies"][item["comp"]]
        results = [judge_once(item, comp, client) for _ in range(args.runs)]
        bands = [r["band"] for r in results]
        oks = [passed(item, b) for b in bands]
        if item["kind"] == "junk":
            junk_runs += len(bands)
            junk_lenient += sum(1 for b in bands if b in ("solid", "strong"))
        else:
            ctrl_runs += len(bands)
            ctrl_ok += sum(oks)
        ticked = Counter(k for r in results for k, v in r["checks"].items() if v)
        rows.append({"id": item["id"], "kind": item["kind"], "expect": item["expect"], "bands": bands,
                     "points": [r["points"] for r in results], "ok": all(oks),
                     "drift": len(set(bands)) > 1,
                     "ticked": ", ".join(f"{k}×{n}" for k, n in ticked.items()) or "—"})
        print(f"{'PASS' if all(oks) else 'FAIL'}  {item['id']:<24} {bands}", flush=True)

    lines = [
        f"# Practice-judge leniency — {len(items)} items × {args.runs} runs",
        "",
        f"- **False-solid rate (junk):** {junk_lenient}/{junk_runs}"
        + (f" = {100 * junk_lenient / junk_runs:.0f}%" if junk_runs else ""),
        f"- **Control pass rate:** {ctrl_ok}/{ctrl_runs}" + (f" = {100 * ctrl_ok / ctrl_runs:.0f}%" if ctrl_runs else ""),
        f"- **Items with drift across runs:** {sum(r['drift'] for r in rows)}/{len(rows)}",
        "",
        "| Item | Kind | Expect | Bands per run | Points | Checks ticked (all runs) | OK |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['kind']} | {r['expect']} | {' · '.join(r['bands'])} | "
                     f"{' · '.join(str(p) for p in r['points'])} | {r['ticked']} | {'✅' if r['ok'] else '❌'} |")
    report = "\n".join(lines)
    print("\n" + report)
    if args.out:
        Path(args.out).write_text(report + "\n")


if __name__ == "__main__":
    main()
