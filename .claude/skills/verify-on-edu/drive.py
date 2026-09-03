"""Local Playwright driver — smoke the deployed jobbotv2-edu Profile / gap map
from a real browser (the client-side bits unit tests can't see: sub-tab switch,
3-pillar layout, popover, horizontal-scroll, ✕ dismiss removes a pill).

Run with the repo venv (has playwright + chromium):
    .venv/bin/python .claude/skills/verify-on-edu/drive.py https://jobbotv2-edu.fly.dev /tmp/edu_shots

Exits non-zero if any hard check fails. Screenshots land in the out dir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://jobbotv2-edu.fly.dev"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/edu_shots")
OUT.mkdir(parents=True, exist_ok=True)

results: dict[str, object] = {}
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results[name] = {"pass": bool(cond), "detail": detail}
    if not cond:
        failures.append(f"{name}: {detail}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{BASE}/profile", wait_until="networkidle", timeout=30000)

    # Gap map lazy-loads via htmx on load — wait for a pill.
    try:
        page.wait_for_selector("#gap-map .group", timeout=20000)
    except Exception as e:  # noqa: BLE001
        check("gap_map_renders", False, f"no pill appeared: {e}")
        page.screenshot(path=str(OUT / "01_market_NO_PILLS.png"), full_page=True)
        print(json.dumps(results, indent=2)); browser.close(); sys.exit(1)

    pill_count = page.locator("#gap-map .group").count()
    pillar_cards = page.locator("#gap-map .card").count()
    check("gap_map_renders", pill_count > 0, f"{pill_count} pills")
    check("three_pillars", pillar_cards == 3, f"{pillar_cards} pillar cards")
    page.screenshot(path=str(OUT / "01_market_tab.png"), full_page=True)

    # Horizontal scroll must NOT appear (popover clamps to viewport).
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("no_horizontal_scroll", overflow <= 1, f"overflow={overflow}px")

    # Context lenses (REQ-020 Phase 2): All / Top 3 / Job-specific live INSIDE
    # #gap-map (the profile sub-tabs are outside it).
    def gap_canons() -> set[str]:
        return {t.strip() for t in page.locator("#gap-map .group .font-medium").all_inner_texts()}

    ctx_tabs = page.locator("#gap-map [role=tab]")
    check("context_tabs_present", ctx_tabs.count() == 3, f"{ctx_tabs.count()} context tabs")
    all_canons = gap_canons()

    ctx_tabs.nth(1).click()   # Top 3 Closest
    page.wait_for_selector("#gap-map .group", timeout=10000)
    page.wait_for_timeout(500)
    top3_canons = gap_canons()
    check("top3_lens_narrows", bool(top3_canons) and top3_canons < all_canons,
          f"all={sorted(all_canons)} top3={sorted(top3_canons)}")
    page.screenshot(path=str(OUT / "05_top3_lens.png"), full_page=True)

    page.locator("#gap-map [role=tab]").nth(2).click()   # Job Specific
    page.wait_for_timeout(700)
    check("job_lens_dropdown", page.locator("#gap-map select").count() == 1, "job dropdown present")
    page.screenshot(path=str(OUT / "06_job_lens.png"), full_page=True)

    page.locator("#gap-map [role=tab]").nth(0).click()   # back to All
    page.wait_for_selector("#gap-map .group", timeout=10000)
    page.wait_for_timeout(400)

    # Sub-tab switch → Parsed Resume & Details.
    page.get_by_role("tab").nth(1).click()
    page.wait_for_timeout(400)
    resume_visible = page.get_by_text("Regenerate cleanly").is_visible()
    check("resume_tab_switches", resume_visible, "resume tab content visible")
    page.screenshot(path=str(OUT / "02_resume_tab.png"), full_page=True)

    # Back to market, open a popover (hover reveals grouped terms + hook).
    page.get_by_role("tab").nth(0).click()
    page.wait_for_timeout(300)
    first = page.locator("#gap-map .group").first
    first.hover()
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "03_popover.png"), full_page=True)

    # ✕ dismiss removes the pill (htmx outerHTML swap → empty).
    before = page.locator("#gap-map .group").count()
    first.hover()
    first.get_by_role("button").first.click()
    page.wait_for_timeout(800)
    after = page.locator("#gap-map .group").count()
    check("dismiss_removes_pill", after == before - 1, f"{before} → {after}")
    page.screenshot(path=str(OUT / "04_after_dismiss.png"), full_page=True)

    browser.close()

print(json.dumps(results, indent=2))
print(f"\nscreenshots → {OUT}")
if failures:
    print("FAILURES:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
