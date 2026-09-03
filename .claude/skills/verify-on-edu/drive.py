"""Local Playwright driver — smoke the deployed jobbotv2-edu Profile shell from a
real browser (the client-side bits unit tests can't see).

Updated for REQ-021 (profile shell): a PERSISTENT résumé header sits above the
sub-tabs; default tab is now **My Profile & Skills** (inline ATS report card +
parsed-section readout); **Market Fit & Gaps** holds the REQ-020 gap map. So the
driver: loads → checks the header + inline ATS card on the default tab → switches
to Market → runs the gap-map checks (3 pillars, no h-scroll, context lenses,
popover, ✕ dismiss) → confirms the header persists across the switch.

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

    # ── DEFAULT TAB — My Profile & Skills ────────────────────────────────
    # Persistent header: résumé filename + ATS badge live ABOVE the tabs.
    header_filename = page.get_by_role("heading", name="__SMOKE_gapmap__.docx").first
    check("header_resume_present", header_filename.is_visible(),
          "résumé filename in persistent header")

    # The header owns the single big ATS number (score from run_checks).
    ats_badge = page.locator("text=/^ATS$/").first
    check("header_ats_badge", ats_badge.is_visible(), "ATS label in header")

    # Inline ATS report card (replaces the old See-report modal). Match the
    # card title; fall back to a looser contains() in case of locale.
    ats_card = page.get_by_text("ATS report & recommendations", exact=False)
    check("inline_ats_card", ats_card.count() >= 1, f"{ats_card.count()} ATS report card(s)")

    # Parsed-section readout now lives in this tab (Regenerate cleanly button).
    check("parsed_readout_here", page.get_by_text("Regenerate cleanly").is_visible(),
          "parsed readout on default tab")

    # AI first-read lazy-loads into the header; give it a beat then shoot.
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "01_profile_tab.png"), full_page=True)

    # No horizontal scroll on the default tab.
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("no_hscroll_profile", overflow <= 1, f"overflow={overflow}px")

    # ── SWITCH → Market Fit & Gaps ───────────────────────────────────────
    page.get_by_role("tab", name="Market Fit & Gaps").click()
    try:
        page.wait_for_selector("#gap-map .group", state="visible", timeout=20000)
    except Exception as e:  # noqa: BLE001
        check("gap_map_renders", False, f"no pill appeared: {e}")
        page.screenshot(path=str(OUT / "02_market_NO_PILLS.png"), full_page=True)
        print(json.dumps(results, indent=2)); browser.close(); sys.exit(1)

    pill_count = page.locator("#gap-map .group").count()
    pillar_cards = page.locator("#gap-map .card").count()
    check("gap_map_renders", pill_count > 0, f"{pill_count} pills")
    check("three_pillars", pillar_cards == 3, f"{pillar_cards} pillar cards")

    # Header must STILL be visible after the tab switch (it's outside the tabs).
    check("header_persists", header_filename.is_visible(),
          "résumé header persists across tab switch")
    page.screenshot(path=str(OUT / "02_market_tab.png"), full_page=True)

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    check("no_horizontal_scroll", overflow <= 1, f"overflow={overflow}px")

    # Context lenses (REQ-020 Phase 2) live INSIDE #gap-map.
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
    page.screenshot(path=str(OUT / "03_top3_lens.png"), full_page=True)

    page.locator("#gap-map [role=tab]").nth(2).click()   # Job Specific
    page.wait_for_timeout(700)
    check("job_lens_dropdown", page.locator("#gap-map select").count() == 1, "job dropdown present")

    page.locator("#gap-map [role=tab]").nth(0).click()   # back to All
    page.wait_for_selector("#gap-map .group", timeout=10000)
    page.wait_for_timeout(400)

    # Popover on hover (grouped terms + defense hook).
    first = page.locator("#gap-map .group").first
    first.hover()
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "04_popover.png"), full_page=True)

    # ✕ dismiss removes the pill (htmx outerHTML swap).
    before = page.locator("#gap-map .group").count()
    first.hover()
    first.get_by_role("button").first.click()
    page.wait_for_timeout(800)
    after = page.locator("#gap-map .group").count()
    check("dismiss_removes_pill", after == before - 1, f"{before} → {after}")
    page.screenshot(path=str(OUT / "05_after_dismiss.png"), full_page=True)

    browser.close()

print(json.dumps(results, indent=2))
print(f"\nscreenshots → {OUT}")
if failures:
    print("FAILURES:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
