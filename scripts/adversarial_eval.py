"""EXP-001 evaluation harness — resume quality A/B test (Eduardo, 2026-09-14/15).

The runnable engine behind docs/experiments/EXP-001-resume-quality-ab-test.md.
Question: do Jobot-tailored resumes beat the original on ATS + a recruiter
screen, and does the B (XYZ quantification) change help WITHOUT hurting honesty?

ARMS per job (within-subject):
  - original   — the untailored resume, the H3 baseline
  - <level>    — tailored at each level (conservative / balanced / aggressive)
Jobs are STRATIFIED: `--matched` in-domain fits + `--stretch` adjacent reaches,
analysed separately so mismatch can't drown the signal.

Each arm runs on the OUTPUT:
  - JUDGE 1  heuristic ATS       (core.resume.ats.run_checks)        0-100
  - JUDGE 2  Gemini recruiter    (core.resume.recruiter_judge.judge) — the fast
             IN-LOOP baseline only; the trusted screen is the independent
             Claude subagent judged out-of-band over `--export-dir` (EXP-001 §5)
  - JUDGE 3  structure/format    (rides along with ATS structure issues)
plus score stability (v24 content-cache guard) and honest cosine movement.

The report leads with an EXECUTIVE SUMMARY: H3 (tailoring > original), H4
(Spearman score↔recruiter on matched jobs ≥0.4, else finding C), score integrity.

WHY the export: Gemini writes AND judges here — judge-and-party. `--export-dir`
dumps every generated resume so a DIFFERENT model (a Claude subagent) can screen
them blind; the Gemini decision is kept only to measure agreement, never shown.

Run:
    # full run on Eduardo (BI): 3 matched + 2 stretch, all levels
    .venv/bin/python scripts/adversarial_eval.py --resume-id 14
    # generate + export for the independent Claude judge
    .venv/bin/python scripts/adversarial_eval.py --resume-id 14 --matched 2 --stretch 1 \\
        --levels balanced aggressive --export-dir data/judge_edu
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.llm.gemini import GeminiClient, resolve_api_key
from core.llm.prompts import LEVEL_RULES
from core.llm.rewrite import rewrite_resume, tailored_to_text
from core.matching import lite_score
from core.matching import semantic_score as ss
from core.resume import ats, recruiter_judge
from core.resume.parser import _common_parse

FIXTURES_DIR = APP_ROOT / "data" / "bakeoff_fixtures"
DB_PATH = APP_ROOT / "data" / "jobot.db"
ALL_LEVELS = ("conservative", "balanced", "aggressive")


# ---------- inputs ----------

def load_fixture(name: str) -> tuple[dict, str]:
    """Fixture .txt → (parsed dict, flattened original text)."""
    path = FIXTURES_DIR / (name if name.endswith(".txt") else f"{name}.txt")
    if not path.exists():
        avail = ", ".join(p.stem for p in FIXTURES_DIR.glob("*.txt"))
        sys.exit(f"Fixture not found: {path.name}. Available: {avail}")
    text = path.read_text(encoding="utf-8")
    parsed = _common_parse(text)
    parsed["source_format"] = ""   # a .txt has no docx/pdf layout to judge
    return parsed, text


def load_db_resume(resume_id: int) -> tuple[dict, str, int]:
    """Real resume from the DB → (parsed dict, original text, resume_id).
    Using a real resume means persona_line resolves the actual role/domain and
    lite_score picks genuinely in-domain jobs — the matched-pair setup B needs
    to prove itself (a domain mismatch can't surface metrics that aren't there)."""
    import json as _json
    from core import db
    with db.connect() as con:
        row = con.execute("SELECT parsed_json FROM resumes WHERE id = ?", (resume_id,)).fetchone()
    if not row:
        sys.exit(f"No resume with id {resume_id} in the DB.")
    parsed = _json.loads(row["parsed_json"])
    parsed.setdefault("source_format", parsed.get("source_format") or "")
    text = (parsed.get("raw_text") or "").strip()
    return parsed, text, resume_id


def pick_jobs(resume_text: str, n: int) -> list[dict]:
    """Rank all described jobs by local coverage against the resume, then take
    a SPREAD: mostly top matches (the sharp question is 'is the output good even
    on the best-matched jobs?') plus a couple of mid-pack stretches for contrast.
    Deterministic."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, title, company, location, description FROM jobs "
        "WHERE description IS NOT NULL AND length(description) > 400"
    ).fetchall()
    con.close()
    jobs = [dict(r) for r in rows]
    if not jobs:
        sys.exit("No jobs with descriptions in the DB — nothing to evaluate.")

    ranked = lite_score.rank(resume_text, jobs)
    n = min(n, len(ranked))
    n_top = max(1, round(n * 0.6))
    picked = ranked[:n_top]
    remainder = n - n_top
    if remainder > 0:
        pool = ranked[n_top:]
        # Evenly sample the rest across the mid/lower pack for contrast.
        step = max(1, len(pool) // (remainder + 1))
        picked += [pool[min(step * (i + 1), len(pool) - 1)] for i in range(remainder)]
    return picked[:n]


def pick_jobs_stratified(resume_text: str, n_matched: int, n_stretch: int) -> list[dict]:
    """Return jobs tagged by stratum: `n_matched` genuine in-domain fits (top of
    the coverage ranking) + `n_stretch` adjacent reaches (mid-pack). EXP-001
    analyses the two strata SEPARATELY so domain mismatch can't drown the signal
    (the probe's mistake). Each dict carries a `_stratum` key. Deterministic.

    lite_score gives the shortlist; the top slice is 'matched' and a mid slice is
    'stretch'. It's a heuristic label — a human confirm pass belongs on top of
    this before trusting the matched bucket (EXP-001 §2)."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, title, company, location, description FROM jobs "
        "WHERE description IS NOT NULL AND length(description) > 400"
    ).fetchall()
    con.close()
    jobs = [dict(r) for r in rows]
    if not jobs:
        sys.exit("No jobs with descriptions in the DB — nothing to evaluate.")

    ranked = lite_score.rank(resume_text, jobs)
    matched = ranked[:n_matched]
    for j in matched:
        j["_stratum"] = "matched"
    # Stretch: pull from the second quartile band — adjacent, not top, not garbage.
    start = max(n_matched, len(ranked) // 4)
    pool = ranked[start:]
    step = max(1, len(pool) // (n_stretch + 1))
    stretch = [pool[min(step * (i + 1), len(pool) - 1)] for i in range(n_stretch)] if pool else []
    for j in stretch:
        j["_stratum"] = "stretch"
    return matched + stretch


# ---------- per-cell evaluation ----------

def evaluate_cell(parsed: dict, original_text: str, job: dict, client: GeminiClient,
                  *, level: str | None, resume_id: int | None = None) -> dict:
    """Run every judge on ONE arm and return a cell. `level=None` is the ORIGINAL
    (untailored) baseline arm (EXP-001 H3); otherwise tailor at `level`. Never
    raises — a failure is recorded so one bad arm doesn't sink the run.

    The generated resume TEXT is kept on the cell (`resume_text`) so the export
    step can dump it for the independent Claude-subagent judge (EXP-001 §5) —
    Gemini here is only the fast in-loop baseline judge; the real screen is done
    out-of-band by a different model to escape judge-and-party."""
    arm = "original" if level is None else level
    cell: dict = {"arm": arm, "level": level,
                  "stratum": job.get("_stratum", "?"), "error": None}

    if level is None:
        tailored_text = original_text
        cell["change"] = "(untailored baseline)"
    else:
        try:
            tailored = rewrite_resume(parsed, job.get("description") or "", level, client,
                                      resume_id=resume_id)
            tailored_text = tailored_to_text(tailored)
        except Exception as e:  # noqa: BLE001 — harness must survive any single failure
            cell["error"] = f"tailor failed: {e}"
            return cell
        cell["change"] = (tailored.get("tailoring_change") or {}).get("one_liner", "")
        cell["warnings"] = len(tailored.get("tailoring_warnings") or [])

    cell["resume_text"] = tailored_text

    # JUDGE 1 + 3: heuristic ATS on the re-parsed OUTPUT (structure rides along).
    out_parsed = _common_parse(tailored_text)
    out_parsed["source_format"] = ""
    ats_res = ats.run_checks(out_parsed)
    cell["ats_score"] = ats_res["score"]
    cell["ats_critical"] = [i for i in ats_res["issues"] if i["severity"] == "critical"]
    cell["ats_structure"] = [i for i in ats_res["issues"]
                             if i["category"] == "structure" and i["severity"] != "info"]

    # JUDGE 2 (in-loop baseline): Gemini recruiter. Compared later against the
    # independent Claude subagent, which is the verdict we actually trust.
    verdict = recruiter_judge.judge(tailored_text, job, client)
    cell["recruiter"] = verdict.to_dict() if verdict else None

    # SCORE + stability guard (v24 content cache ⇒ 2nd call is a lookup).
    s1 = ss.score_single_no_cache(tailored_text, job, client, resume_id=resume_id)
    s2 = ss.score_single_no_cache(tailored_text, job, client, resume_id=resume_id)
    if s1 and s2:
        cell["score_a"], cell["score_b"] = s1.score, s2.score
        cell["score_stable"] = s1.score == s2.score
    else:
        cell["score_a"] = cell["score_b"] = None
        cell["score_stable"] = None

    # HONEST MOVEMENT vs the JD (0 for the original arm by definition).
    try:
        d = lite_score.delta(original_text, tailored_text, job.get("description") or "")
        cell["cosine_delta"] = d["delta"]
    except Exception:  # noqa: BLE001
        cell["cosine_delta"] = None

    return cell


# ---------- analysis (EXP-001 hypotheses) ----------

def _axis(cell: dict, axis: str):
    rec = cell.get("recruiter")
    return rec["axes"].get(axis) if rec else None


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _score_recruiter_corr(cells_by_job, stratum: str | None = "matched"):
    """Spearman ρ between Jobot's fit score and the recruiter's decision (H4).
    Restricted to `stratum` (matched by default) so a shelf of correctly-rejected
    stretches doesn't fake a correlation. Returns (rho, n) or (None, n)."""
    xs, ys = [], []
    for _job, cells in cells_by_job:
        for c in cells:
            if c.get("error") or c.get("level") is None:
                continue
            if stratum and c.get("stratum") != stratum:
                continue
            rec = c.get("recruiter")
            if rec and c.get("score_a") is not None:
                xs.append(c["score_a"])
                ys.append(rec["decision_score"])
    if len(xs) < 3:
        return (None, len(xs))
    try:
        from scipy.stats import spearmanr
        rho = spearmanr(xs, ys).correlation
        return (None if rho != rho else float(rho), len(xs))   # NaN guard
    except Exception:  # noqa: BLE001
        return (None, len(xs))


# ---------- report ----------

def _fmt_recruiter(rec: dict | None) -> str:
    if not rec:
        return "—"
    axes = rec["axes"]
    ax = "/".join(str(axes[a]) for a in recruiter_judge.RUBRIC_AXES)
    return f"{rec['decision']} ({rec['rubric_total']}/25 · {ax})"


def build_report(subject: str, persona_note: str, cells_by_job: list[tuple[dict, list[dict]]],
                 levels: tuple[str, ...]) -> str:
    L: list[str] = []
    tailored = [c for _, cells in cells_by_job for c in cells
                if not c.get("error") and c.get("level") is not None]
    originals = [c for _, cells in cells_by_job for c in cells
                 if not c.get("error") and c.get("level") is None]
    all_cells = tailored + originals

    L.append(f"# EXP-001 run — `{subject}`\n")
    L.append(f"_Generated {date.today().isoformat()} · in-loop judge: Gemini (baseline). "
             f"Trust the independent Claude-subagent verdicts (judged out-of-band)._\n")
    L.append(f"- Persona: {persona_note}")
    n_matched = len({job['id'] for job, _ in cells_by_job if job.get('_stratum') == 'matched'})
    n_stretch = len({job['id'] for job, _ in cells_by_job if job.get('_stratum') == 'stretch'})
    L.append(f"- Jobs: {len(cells_by_job)} ({n_matched} matched · {n_stretch} stretch)")
    L.append(f"- Arms: original baseline + levels [{', '.join(levels)}]\n")

    # ---- executive summary (the hypotheses) ----
    L.append("## Executive summary\n")
    drift = [c for c in all_cells if c.get("score_stable") is False]
    L.append(f"- **Score integrity (regression guard):** "
             f"{'✅ stable on all ' + str(len(all_cells)) + ' cells' if not drift else f'❌ DRIFTED on {len(drift)} cell(s)'}")

    if originals and tailored:
        o_rm = _mean([_axis(c, "requirement_match") for c in originals])
        t_rm = _mean([_axis(c, "requirement_match") for c in tailored])
        o_ats = _mean([c["ats_score"] for c in originals])
        t_ats = _mean([c["ats_score"] for c in tailored])
        L.append(f"- **H3 · tailoring beats original:** requirement_match {o_rm}→{t_rm}, "
                 f"ATS {o_ats if o_ats is None else round(o_ats)}→{t_ats if t_ats is None else round(t_ats)}")

    rho, rn = _score_recruiter_corr(cells_by_job, "matched")
    if rho is not None:
        h4 = "✅ tracks" if rho >= 0.4 else "❌ WEAK — score misleads (finding C)"
        L.append(f"- **H4 · score↔recruiter (matched, n={rn}):** Spearman ρ={rho:+.2f} → {h4}")
    else:
        L.append(f"- **H4 · score↔recruiter:** not enough matched data (n={rn}).")

    recs = [c["recruiter"] for c in tailored if c.get("recruiter")]
    if recs:
        adv = sum(1 for r in recs if r["decision"] == "advance")
        L.append(f"- **Recruiter advance rate (tailored):** {adv}/{len(recs)} ({100*adv//len(recs)}%)")
    L.append("")

    # ---- per-job detail ----
    L.append("## Cells\n")
    for job, cells in cells_by_job:
        title = (job.get("title") or "?")[:66]
        company = job.get("company") or "?"
        L.append(f"### [{job.get('_stratum','?')}] {title} — {company}")
        L.append(f"`{job['id']}`\n")
        L.append("| Arm | ATS | Recruiter (rubric) | Fit | Stable | Δcos | Changed |")
        L.append("|---|---|---|---|---|---|---|")
        for c in cells:
            if c.get("error"):
                L.append(f"| {c['arm']} | — | ERROR: {c['error']} | — | — | — | — |")
                continue
            sa = c.get("score_a")
            stable = {True: "✅", False: "❌", None: "·"}[c.get("score_stable")]
            dc = c.get("cosine_delta")
            dc_s = f"{dc:+.3f}" if isinstance(dc, float) else "—"
            L.append(f"| {c['arm']} | {c['ats_score']} | {_fmt_recruiter(c.get('recruiter'))} "
                     f"| {sa if sa is not None else '—'} | {stable} | {dc_s} | {c.get('change','')[:34]} |")
        L.append("")
        for c in cells:
            if c.get("error"):
                continue
            notes: list[str] = []
            for i in c.get("ats_critical", []):
                notes.append(f"ATS critical — {i['message']}")
            rec = c.get("recruiter")
            if rec:
                if rec.get("one_liner"):
                    notes.append(f"recruiter: “{rec['one_liner']}”")
                for r in rec.get("reject_reasons", []):
                    notes.append(f"reject reason — {r}")
            if notes:
                L.append(f"**{c['arm']}:**")
                for nline in notes:
                    L.append(f"  - {nline}")
                L.append("")
    return "\n".join(L)


# ---------- main ----------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", default="sara_hr", help="fixture name in data/bakeoff_fixtures/")
    ap.add_argument("--resume-id", type=int, default=None,
                    help="score a REAL resume from the DB by id (overrides --fixture) — "
                         "real persona + in-domain jobs, the matched-pair setup EXP-001 needs")
    ap.add_argument("--matched", type=int, default=3, help="# in-domain 'matched' jobs")
    ap.add_argument("--stretch", type=int, default=2, help="# adjacent 'stretch' jobs")
    ap.add_argument("--levels", nargs="+", default=list(ALL_LEVELS), choices=ALL_LEVELS)
    ap.add_argument("--baseline", action="store_true", default=True,
                    help="include the untailored original-resume arm (H3); on by default")
    ap.add_argument("--no-baseline", dest="baseline", action="store_false")
    ap.add_argument("--export-dir", default=None,
                    help="also dump each generated resume + a judge_manifest.json here, "
                         "so an independent Claude subagent can screen them (EXP-001 §5)")
    ap.add_argument("--out", default=None, help="report path (default data/exp001_<subject>_<date>.md)")
    args = ap.parse_args()

    levels = tuple(dict.fromkeys(args.levels))

    if args.resume_id is not None:
        parsed, original_text, resume_id = load_db_resume(args.resume_id)
        label = f"resume#{resume_id}"
    else:
        parsed, original_text = load_fixture(args.fixture)
        resume_id = None
        label = args.fixture
    jobs = pick_jobs_stratified(original_text, args.matched, args.stretch)

    client = GeminiClient(api_key=resolve_api_key())

    arms_per_job = (1 if args.baseline else 0) + len(levels)
    print(f"Subject: {label} · jobs: {len(jobs)} ({args.matched} matched + {args.stretch} stretch)")
    print(f"Arms/job: {arms_per_job} (baseline={args.baseline}, levels={list(levels)}) "
          f"→ {len(jobs) * arms_per_job} cells\n")

    cells_by_job: list[tuple[dict, list[dict]]] = []
    for ji, job in enumerate(jobs, 1):
        strat = job.get("_stratum", "?")
        print(f"[{ji}/{len(jobs)}] ({strat}) {(job.get('title') or '?')[:46]} — {job.get('company') or '?'}")
        cells = []
        plan: list[str | None] = ([None] if args.baseline else []) + list(levels)
        for level in plan:
            arm = "original" if level is None else level
            print(f"    · {arm} …", end="", flush=True)
            cell = evaluate_cell(parsed, original_text, job, client,
                                 level=level, resume_id=resume_id)
            if cell.get("error"):
                print(f" ERROR ({cell['error']})")
            else:
                rec = cell.get("recruiter")
                dec = rec["decision"] if rec else "n/a"
                print(f" ATS {cell['ats_score']} · {dec} · fit {cell.get('score_a')} "
                      f"{'' if cell.get('score_stable') is not False else 'DRIFT!'}")
            cells.append(cell)
        cells_by_job.append((job, cells))

    if resume_id is not None:
        from core.resume import ai_summary
        persona_note = f"real — {ai_summary.persona_line(resume_id)}"
    else:
        persona_note = "generic (fixture not in DB → GENERIC_PERSONA)"
    report = build_report(label, persona_note, cells_by_job, levels)

    safe = label.replace("#", "")
    out = Path(args.out) if args.out else (APP_ROOT / "data" / f"exp001_{safe}_{date.today().isoformat()}.md")
    if not out.is_absolute():
        out = (APP_ROOT / out)
    out.write_text(report, encoding="utf-8")
    print(f"\nReport written → {out}")

    if args.export_dir:
        n = export_for_judge(label, cells_by_job, Path(args.export_dir))
        print(f"Exported {n} resumes for the independent judge → {args.export_dir}/judge_manifest.json")


def export_for_judge(subject: str, cells_by_job, out_dir: Path) -> int:
    """Dump every generated resume + its job to `out_dir` so an INDEPENDENT judge
    (a Claude subagent, a different model than the Gemini that wrote them) can
    screen them blind. Writes one .txt per arm plus a judge_manifest.json listing
    {id, job_title, job_description, resume_file, gemini_decision} — the Gemini
    call is kept only so we can later measure agreement, NOT shown to the judge."""
    import json as _json
    out_dir = out_dir if out_dir.is_absolute() else (APP_ROOT / out_dir)
    resumes_dir = out_dir / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for job, cells in cells_by_job:
        for c in cells:
            if c.get("error") or not c.get("resume_text"):
                continue
            cid = f"{job['id']}__{c['arm']}".replace("·", "_").replace("/", "_")
            fname = f"{cid}.txt"
            (resumes_dir / fname).write_text(c["resume_text"], encoding="utf-8")
            rec = c.get("recruiter") or {}
            manifest.append({
                "id": cid,
                "arm": c["arm"],
                "stratum": c.get("stratum"),
                "job_title": job.get("title"),
                "job_company": job.get("company"),
                "job_description": (job.get("description") or "")[:4000],
                "resume_file": f"resumes/{fname}",
                "gemini_decision": rec.get("decision"),   # for agreement scoring only
                "gemini_fit_score": c.get("score_a"),
            })
    (out_dir / "judge_manifest.json").write_text(
        _json.dumps({"subject": subject, "items": manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return len(manifest)


if __name__ == "__main__":
    main()
