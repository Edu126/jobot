"""Local Playwright driver — smoke the deployed jobbotv2-edu Profile shell from a
real browser (the client-side bits unit tests can't see).

Updated for REQ-021 (profile shell): a PERSISTENT résumé header sits above the
sub-tabs; default tab is now **My Profile & Skills** (inline ATS report card +
parsed-section readout); **Market Fit & Gaps** holds the REQ-020 gap map. So the
driver: loads → checks the header + inline ATS card on the default tab → switches
to Market → runs the gap-map checks (3 pillars, no h-scroll, the >70 filter
dropping low-fit gaps, frequency bars, popover, ✕ dismiss, Rebuild) → confirms the
header persists across the switch. (REQ-036/ADR-040: the All/Top-3/Job lens
switcher is gone — single recent/high-fit lens + a Rebuild flush.)

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
    # Web-first (ADR-033): capture at a wide desktop workspace.
    page = browser.new_page(viewport={"width": 1440, "height": 900})
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

    def gap_canons() -> set[str]:
        return {t.strip() for t in page.locator("#gap-map .group .font-medium").all_inner_texts()}

    # REQ-036 / ADR-040: single lens (the All/Top-3/Job switcher was removed).
    check("no_context_tabs", page.locator("#gap-map [role=tab]").count() == 0,
          "lens switcher removed")
    all_canons = gap_canons()

    # The >70 filter must drop the ≤70 fixture jobs' gaps (Terraform/Power BI/Docker
    # live only in the score-40/20 jobs); Kubernetes (from the 92/85/78 jobs) stays.
    low_fit = {"Terraform", "Power BI", "Docker"} & all_canons
    check("highfit_filter_drops_lowfit", not low_fit,
          f"low-fit gaps leaked: {sorted(low_fit)} | shown={sorted(all_canons)}")
    check("highfit_gap_present", "Kubernetes" in all_canons,
          f"Kubernetes (from >70 jobs) shown | shown={sorted(all_canons)}")

    # Frequency bar (REQ-036): each pill carries an inline width-styled bar.
    check("frequency_bars_present",
          page.locator("#gap-map .group [style*='width']").count() > 0,
          f"{page.locator('#gap-map .group [style*=width]').count()} bars")

    # Rebuild button (flush) present in the panel header.
    check("rebuild_button_present",
          page.get_by_role("button", name="Rebuild").count() >= 1, "Rebuild button")

    # Popover on hover (grouped terms + defense hook).
    first = page.locator("#gap-map .group").first
    first.hover()
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / "04_popover.png"), full_page=True)

    # ✕ dismiss re-renders the map without the pill (REQ-021: full-map swap).
    before = page.locator("#gap-map .group").count()
    first.hover()
    first.get_by_role("button").first.click()
    page.wait_for_selector("#gap-map .group", timeout=10000)
    page.wait_for_timeout(600)
    after = page.locator("#gap-map .group").count()
    check("dismiss_removes_pill", after == before - 1, f"{before} → {after}")
    page.screenshot(path=str(OUT / "05_after_dismiss.png"), full_page=True)

    # Hidden-gaps footer appears (REQ-021) — the reverse of the ✕.
    hidden = page.get_by_text("Hidden gaps", exact=False)
    check("hidden_gaps_footer", hidden.count() >= 1, "hidden-gaps fold present after dismiss")

    # Restore from the footer → the cluster comes back (count returns).
    if hidden.count():
        hidden.first.click()                       # open the <details>
        page.wait_for_timeout(300)
        page.locator("#gap-map details button").first.click()
        page.wait_for_selector("#gap-map .group", timeout=10000)
        page.wait_for_timeout(600)
        restored = page.locator("#gap-map .group").count()
        check("restore_brings_pill_back", restored == before, f"{after} → {restored}")
        page.screenshot(path=str(OUT / "06_after_restore.png"), full_page=True)

    # Rebuild flush (REQ-036): posts, re-renders the panel without erroring. On a
    # keyless -edu the reclassify can't run, so gaps degrade to honest real/domain
    # — the map must still render (pills present), not blank/500. Done LAST since
    # it wipes the fixture's cached classifications (restore reseeds afterwards).
    page.get_by_role("button", name="Rebuild").first.click()
    try:
        page.wait_for_selector("#gap-map .group", state="visible", timeout=15000)
        rebuilt = page.locator("#gap-map .group").count()
        check("rebuild_rerenders", rebuilt > 0, f"{rebuilt} pills after Rebuild")
    except Exception as e:  # noqa: BLE001
        check("rebuild_rerenders", False, f"map blank/errored after Rebuild: {e}")
    page.screenshot(path=str(OUT / "07_after_rebuild.png"), full_page=True)

    # ── PREP surface (REQ-023/025) — for the REQ-027 stranger page ────────
    # Non-fatal: a hiccup here must not lose the gap-map shots above.
    try:
        page.goto(f"{BASE}/prep", wait_until="networkidle", timeout=30000)
        page.locator("a[href^='/prep/']").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)   # fit context bar + lazy kit fragment
        # Fit context bar (score + reasoning + matched/gaps) at the top.
        page.screenshot(path=str(OUT / "08_prep_fit.png"), full_page=True)
        # Confirm the cached kit actually rendered (a STAR question is present).
        star = page.get_by_text("regulated program", exact=False)
        check("prep_kit_renders", star.count() >= 1, "STAR question from cached kit")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "09_prep_kit.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        check("prep_surface", False, f"prep capture failed: {e}")

    browser.close()

print(json.dumps(results, indent=2))
print(f"\nscreenshots → {OUT}")
if failures:
    print("FAILURES:\n  " + "\n  ".join(failures))
    sys.exit(1)
print("ALL CHECKS PASSED")
