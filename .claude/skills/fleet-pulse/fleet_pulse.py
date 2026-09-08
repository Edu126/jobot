"""Fleet KPI dashboard — pull each user's Phase 0 KPIs and render ONE view.

Owner-run, local, pull-over-SSH (ADR-035). For each Fly app it runs
`fly ssh console -a <app> -C "python -m core.bi.kpis"` (the deterministic KPI
JSON from ADR-034), aggregates, and writes a single self-contained HTML
dashboard: rollup cards + detailed table + per-user activity sparkline. Each run
appends a rollup line to a local history JSONL so trend lines build over time.

Only aggregate numbers leave each app; raw user data never does.

Usage:
    python3 .claude/skills/fleet-pulse/fleet_pulse.py            # discover jobbotv2* apps
    python3 .claude/skills/fleet-pulse/fleet_pulse.py app1 app2  # explicit apps
Then open the printed HTML path.
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# App → friendly label. NAMES DO NOT MATCH USERS — verify before trusting
# (see memory reference_fly_app_user_mapping). Edit as the fleet changes.
LABELS = {
    "jobbotv2": "Melissa (verify)",
    "jobbotv2-hermana": "Mehran (verify)",
    "jobbotv2-andrea": "Andrea (verify)",
    "jobbotv2-melissa": "Sara (verify)",
    "jobbotv2-edu": "Eduardo (owner)",
}

OUT = Path("/tmp/fleet_pulse.html")
HISTORY = Path.home() / ".jobot" / "fleet_pulse_history.jsonl"


def discover_apps() -> list[str]:
    try:
        r = subprocess.run(["fly", "apps", "list", "--json"],
                           capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout)
        names = [a.get("Name", "") for a in data]
        apps = sorted(n for n in names if n.startswith("jobbotv2"))
        if apps:
            return apps
    except Exception as e:  # noqa: BLE001
        print(f"  (discovery failed: {e}; falling back to known labels)")
    return sorted(LABELS)


def _wake(app: str) -> None:
    """Auto-stopped Fly machines don't wake on `fly ssh`; an HTTP hit does."""
    try:
        subprocess.run(["curl", "-fsS", "--max-time", "25",
                        f"https://{app}.fly.dev/healthz"],
                       capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        pass


def fetch_kpis(app: str) -> dict | None:
    """Run the KPI CLI on the app over SSH; parse the JSON line from stdout."""
    _wake(app)
    try:
        r = subprocess.run(
            ["fly", "ssh", "console", "-a", app, "-C", "python -m core.bi.kpis"],
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  {app}: TIMEOUT")
        return None
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    print(f"  {app}: no KPI JSON (stderr: {r.stderr.strip()[:120]})")
    return None


# ---------- rendering ----------

def _yn(v) -> str:
    if v is None:
        return '<span class="muted">—</span>'
    return '<span class="yes">Yes</span>' if v else '<span class="no">No</span>'


def _pct(v) -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def _sparkline(weekly: list[dict]) -> str:
    """Inline SVG polyline of active-days-per-week (0..7). No JS, no deps."""
    if not weekly:
        return '<span class="muted">—</span>'
    vals = [w.get("active_days", 0) for w in weekly]
    w, h, pad = 90, 22, 2
    n = max(len(vals), 2)
    step = (w - 2 * pad) / (n - 1)
    pts = " ".join(
        f"{pad + i * step:.1f},{h - pad - (v / 7) * (h - 2 * pad):.1f}"
        for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="#0a7" stroke-width="1.5" points="{pts}"/></svg>')


def render(rows: list[dict], history: list[dict]) -> str:
    ok = [r for r in rows if r["kpis"]]
    n = len(ok)

    def count(pred) -> int:
        return sum(1 for r in ok if pred(r["kpis"]))

    active = count(lambda k: k["g1_retention"].get("current_week_active"))
    w1 = count(lambda k: k["g1_retention"].get("w1_retained") is True)
    w4 = count(lambda k: k["g1_retention"].get("w4_retained") is True)
    activated = count(lambda k: k["s1_activation"].get("activated") is True)
    apps_wk = sum((r["kpis"]["g2_applications"]["this_week"] or 0) for r in ok)
    heard = sum((r["kpis"]["outcome"]["heard_back"] or 0) for r in ok)
    applied = sum((r["kpis"]["outcome"]["applied"] or 0) for r in ok)

    cards = [
        ("Users active this week", f"{active}/{n}"),
        ("W1 retained", f"{w1}/{n}"),
        ("W4 retained", f"{w4}/{n}"),
        ("Activated (reached tailor)", f"{activated}/{n}"),
        ("Applications this week", str(apps_wk)),
        ("Heard back / applied", f"{heard}/{applied}"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="lbl">{html.escape(l)}</div>'
        f'<div class="big">{html.escape(v)}</div></div>' for l, v in cards)

    # Aggregate trend: "users active this week" across historical runs.
    trend = _sparkline([{"active_days": (h.get("active") or 0)} for h in history][-20:]) \
        if len(history) >= 2 else '<span class="muted">runs it more to build a trend</span>'

    tr = []
    for r in rows:
        app, k = r["app"], r["kpis"]
        label = LABELS.get(app, "—")
        if not k:
            tr.append(f'<tr><td>{html.escape(label)}</td><td class="mono">{html.escape(app)}</td>'
                      f'<td colspan="9" class="no">unreachable</td></tr>')
            continue
        g1, g2, s1, s2, s3, o = (k["g1_retention"], k["g2_applications"],
                                 k["s1_activation"], k["s2_acceptance"],
                                 k["s3_score_trust"], k["outcome"])
        d = g2["delta"]
        dstr = f'+{d}' if d > 0 else (str(d) if d < 0 else "±0")
        tr.append(
            f'<tr><td>{html.escape(label)}</td><td class="mono">{html.escape(app)}</td>'
            f'<td>{_yn(g1.get("current_week_active"))}</td>'
            f'<td>{_yn(g1.get("w1_retained"))}</td><td>{_yn(g1.get("w4_retained"))}</td>'
            f'<td>{g2["this_week"]} <span class="muted">({dstr})</span></td>'
            f'<td>{_yn(s1.get("activated"))}</td>'
            f'<td>{_pct(s2.get("acceptance_rate"))}</td>'
            f'<td>{"—" if s3.get("mean_applied_score") is None else s3["mean_applied_score"]}</td>'
            f'<td>{_pct(o.get("response_rate"))}</td>'
            f'<td>{_sparkline(g1.get("weekly_active"))}</td></tr>')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><meta charset="utf-8"><title>Jobot fleet pulse</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:2rem;color:#1a1a1a;max-width:1100px}}
 h1{{margin:0 0 .2rem}} .sub{{color:#777;margin-bottom:1.5rem}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;margin-bottom:1.5rem}}
 .card{{border:1px solid #e5e5e5;border-radius:10px;padding:.75rem 1rem}}
 .lbl{{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#888}}
 .big{{font-size:1.7rem;font-weight:600;margin-top:.2rem}}
 table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:.5rem .6rem;border-bottom:1px solid #eee}}
 th{{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:#888}}
 .mono{{font-family:ui-monospace,monospace;font-size:12px;color:#666}}
 .yes{{color:#0a7;font-weight:600}} .no{{color:#c33;font-weight:600}} .muted{{color:#aaa}}
 .trend{{margin:1.5rem 0}}
</style>
<h1>Jobot · fleet pulse</h1>
<div class="sub">{n} reachable of {len(rows)} apps · pulled {now} · deterministic KPIs (ADR-034/035), not LLM</div>
<div class="cards">{card_html}</div>
<div class="trend"><span class="lbl">Trend · users active this week (across runs)</span><br>{trend}</div>
<table>
 <tr><th>User</th><th>App</th><th>Active</th><th>W1</th><th>W4</th><th>Apps/wk</th>
     <th>Activated</th><th>Accept</th><th>Avg score</th><th>Response</th><th>Activity</th></tr>
 {''.join(tr)}
</table>
<p class="sub">Labels are hand-maintained and may be wrong — verify before naming a user.</p>
"""


def main() -> int:
    apps = sys.argv[1:] or discover_apps()
    print(f"Pulling KPIs from {len(apps)} apps: {', '.join(apps)}")
    rows = []
    for app in apps:
        print(f"  {app}…")
        rows.append({"app": app, "kpis": fetch_kpis(app)})

    # Append this run's rollup to history for trend lines.
    ok = [r["kpis"] for r in rows if r["kpis"]]
    rollup = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n": len(ok),
        "active": sum(1 for k in ok if k["g1_retention"].get("current_week_active")),
        "apps_wk": sum((k["g2_applications"]["this_week"] or 0) for k in ok),
    }
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a") as f:
        f.write(json.dumps(rollup) + "\n")
    history = [json.loads(l) for l in HISTORY.read_text().splitlines() if l.strip()]

    OUT.write_text(render(rows, history))
    print(f"\nDashboard → {OUT}\nHistory   → {HISTORY} ({len(history)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
