"""Playwright driver for the fit-story change (2026-09-15) — verify the match
story ('In your lane' / 'Reach — level up' / 'Pivot' / 'Long shot') renders on
the job cards of the deployed -edu /jobs page, and screenshot it to LOOK.

Uses -edu's REAL data (its current résumé + cached scores + ai_summary) — no
seeding: fit labels only need a scored card + a persona summary, both of which
the user's staging already has. Read-only; touches no data.

Run:
    .venv/bin/python .claude/skills/verify-on-edu/drive_fit.py https://jobbotv2-edu.fly.dev /tmp/fit_shots
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://jobbotv2-edu.fly.dev"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/fit_shots")
OUT.mkdir(parents=True, exist_ok=True)

FIT_LABELS = ["In your lane", "Reach — level up", "Pivot — new field",
              "Long shot", "Weak match"]

results: dict[str, object] = {}
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results[name] = {"pass": bool(cond), "detail": detail}
    if not cond:
        failures.append(f"{name}: {detail}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/jobs", wait_until="networkidle", timeout=40000)
    page.wait_for_timeout(2000)   # let top-matches + any lazy score swaps settle

    cards = page.locator("article[data-job-id]").count()
    check("cards_present", cards > 0, f"{cards} job cards on /jobs")

    # The list must be CLEAN now — the old fit chips (In your lane / Pivot / …)
    # were removed as clutter (Eduardo 2026-09-15). Assert they're gone.
    chip_hits = {lbl: page.get_by_text(lbl, exact=False).count() for lbl in FIT_LABELS}
    check("no_fit_chips_in_list", sum(chip_hits.values()) == 0,
          f"stale fit chips still present: {chip_hits}")
    page.screenshot(path=str(OUT / "jobs_clean_list.png"), full_page=True)

    # ── DETAIL PANE — job LEVEL (a fact about the vacancy) in the meta line ──
    # Click a card whose title marks a level so a tag is expected. Fall back to
    # the first card if none matched.
    JOB_LEVELS = ["Senior-level role", "Junior-level role", "Leadership role"]
    target = None
    for kw in ("Senior", "Director", "Manager", "Junior", "Lead"):
        loc = page.locator(f"article[data-job-id]:has-text('{kw}')").first
        if loc.count():
            target = loc
            break
    target = target or page.locator("article[data-job-id]").first
    try:
        target.click()
        page.wait_for_timeout(1800)   # HTMX loads /jobs/detail into the pane
        level_hits = sum(page.get_by_text(l, exact=False).count() for l in JOB_LEVELS)
        check("detail_shows_job_level", level_hits > 0,
              f"job-level tag in detail meta (hits {level_hits})")
        page.screenshot(path=str(OUT / "detail_pane.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        check("detail_shows_job_level", False, f"detail capture failed: {e}")

    browser.close()

print(json.dumps(results, indent=2))
print(f"\nscreenshots → {OUT}")
if failures:
    print("FAILURES:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
