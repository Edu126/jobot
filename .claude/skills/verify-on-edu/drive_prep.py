"""Local Playwright driver — smoke the deployed Prep tab (REQ-023) from a real
browser. Language-agnostic: it asserts on FIXTURE content (seeded strings) and
structural hooks, not UI copy, so it passes under either EN or ES.

Flow: /prep list (nav tab + entry form + seeded session card) → submit the entry
form (company+role) → confirm proposal chips → open the seeded session detail →
the lazy company-outlook (3 facets + news) and the STAR/reverse kit render from
cache. Screenshots land in the out dir.

    .venv/bin/python .claude/skills/verify-on-edu/drive_prep.py https://jobbotv2-edu.fly.dev /tmp/prep_shots
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://jobbotv2-edu.fly.dev"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/prep_shots")
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

    # ── 1. the Prep tab: list + entry ───────────────────────────────────
    page.goto(f"{BASE}/prep", wait_until="networkidle", timeout=30000)
    page.screenshot(path=str(OUT / "01_list.png"), full_page=True)

    check("nav_prep_tab", page.locator('a[href="/prep"]').count() >= 1, "Prep tab in nav")
    check("entry_form", page.locator('form[hx-post="/prep/start"]').count() == 1, "entry form present")
    # ADR-030 entry: ONE smart input (link OR pasted JD), company/role optional
    check("smart_input", page.get_by_test_id("prep-smart-input").count() == 1,
          "smart link/JD input present")
    # seeded session card (bound session → shows the company)
    card = page.locator('a[href^="/prep/"]').filter(has_text="CMHC")
    check("seeded_session_card", card.count() >= 1, f"{card.count()} CMHC session card(s)")

    # ── 2. paste capture: multi-line paste collapses to a "N lines pasted" chip
    page.fill('[data-testid="prep-smart-input"]', "Line one\nLine two\nLine three")
    page.wait_for_timeout(300)
    chip = page.get_by_test_id("prep-paste-chip")
    check("paste_chip", chip.is_visible() and "3" in chip.inner_text(),
          f"paste chip shows line count, got '{chip.inner_text().strip() if chip.count() else None}'")
    page.screenshot(path=str(OUT / "02_paste_chip.png"), full_page=True)
    # clear it and use the DB-match path via the optional company/role fields
    page.evaluate("""() => { const el = document.querySelector('[data-testid=prep-smart-input]');
                             el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); }""")
    page.click('button:has-text("optional"), button:has-text("opcional")')
    page.wait_for_timeout(200)
    page.fill('input[name="company"]', "CMHC")
    page.fill('input[name="role_title"]', "Senior Business Analyst")
    page.keyboard.press("Escape")
    page.locator("main").click(position={"x": 5, "y": 5})
    page.wait_for_timeout(200)
    page.click('form[hx-post="/prep/start"] button[type="submit"]')
    try:
        page.wait_for_selector('#prep-entry-result form[hx-post="/prep/confirm"]', timeout=8000)
        confirmed = True
    except Exception:
        confirmed = False
    page.screenshot(path=str(OUT / "03_confirm.png"), full_page=True)
    check("confirm_proposal", confirmed,
          "matching proposed the tailored job as a confirm chip")

    check("list_width_7xl", page.locator("main.max-w-7xl").count() >= 1, "list uses max-w-7xl")

    # ── 3. bound-session detail: outlook + kit + TABS + CHIP-FILTER ACCORDION
    href = card.first.get_attribute("href")
    page.goto(f"{BASE}{href}", wait_until="networkidle", timeout=30000)
    page.wait_for_selector('[data-testid="qa-item"]', timeout=12000)
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / "04_detail_kit.png"), full_page=True)

    body = page.content()
    check("detail_width_7xl", page.locator("main.max-w-7xl").count() >= 1, "detail uses max-w-7xl")
    # REQ-025 fit brief: a qualitative band (NOT a bare %) + narrative +
    # strengths-first / gaps-as-prep-tasks
    fit_band = page.get_by_test_id("fit-band")
    check("fit_band", fit_band.count() == 1, "qualitative fit band shown")
    check("fit_no_bare_pct",
          fit_band.count() == 1 and not any(c.isdigit() for c in fit_band.inner_text()),
          f"band is qualitative, got '{fit_band.inner_text().strip() if fit_band.count() else None}'")
    check("fit_strengths", "ATIP reporting automation" in body, "lean-into strengths rendered")
    check("fit_gaps", "Cloud architecture depth" in body, "be-ready gaps rendered")
    check("outlook_culture", "Public agency" in body, "culture facet rendered")
    # REQ-025 reading aid: key phrases render as <strong>, not literal ** markers
    check("outlook_bold",
          "<strong>Public agency</strong>" in body and "**" not in page.locator("#prep-outlook").inner_text(),
          "outlook key phrases bolded (no literal ** shown)")
    check("outlook_news", "Launched AI Housing Assist" in body, "news item rendered")
    check("tabs_present", page.get_by_test_id("tab-likely").count() == 1
          and page.get_by_test_id("tab-reverse").count() == 1, "both kit tabs present")
    check("kit_star_question", "data process you automated" in body, "question row rendered")
    layers = page.get_by_test_id("kit-layers")
    check("kit_layers", layers.count() == 1 and "CMHC" in layers.inner_text(),
          f"grounded-on layers shown, got '{layers.inner_text().strip() if layers.count() else None}'")

    # kind-chip filter + accordion (replaces the carousel). Chips present; all
    # questions listed at once; expanding one reveals its answer.
    check("qa_chips", page.get_by_test_id("qa-chip").count() >= 2, "kind filter chips present")
    n_items = page.get_by_test_id("qa-item").count()
    check("qa_accordion_list", n_items >= 2, f"all questions listed at once ({n_items})")
    # expand the first question → its STAR answer becomes visible
    first_toggle = page.get_by_test_id("qa-item").first.locator("button").first
    first_toggle.click()
    page.wait_for_timeout(300)
    check("qa_expands", page.get_by_text("An ATIP reporting backlog").is_visible(),
          "expanding a question reveals its answer")
    page.screenshot(path=str(OUT / "05_accordion_open.png"), full_page=True)

    # thumbs inside the expanded panel → "Thanks" (BI-loop feedback fired)
    page.locator('[data-testid="thumb-up"]:visible').first.click()
    try:
        page.wait_for_selector('[data-testid="voted-thanks"]:visible', timeout=6000)
        thanked = True
    except Exception:
        thanked = False
    check("thumbs_feedback", thanked, "thumbs-up shows Thanks (event fired)")

    # chip filter narrows the visible list (Why you → fewer items than All)
    page.get_by_test_id("qa-chip").filter(has_text="Why").first.click()
    page.wait_for_timeout(300)
    visible_after = page.locator('[data-testid="qa-item"]:visible').count()
    check("qa_chip_filters", visible_after < n_items,
          f"chip filter narrows list ({visible_after} < {n_items})")

    # switch to the reverse tab → questions-to-ask list
    page.get_by_test_id("tab-reverse").click()
    page.wait_for_timeout(400)
    check("reverse_tab", page.get_by_text("maturity of your data stack").is_visible(),
          "reverse questions visible after tab switch")
    page.screenshot(path=str(OUT / "05_reverse_tab.png"), full_page=True)

    # ── 4. fallback session: empty outlook → general-prep message ───────
    page.goto(f"{BASE}/prep", wait_until="networkidle", timeout=30000)
    fb = page.locator('a[href^="/prep/"]').filter(has_text="Zorptech")
    check("fallback_card", fb.count() >= 1, "fallback session card present")
    page.goto(f"{BASE}{fb.first.get_attribute('href')}", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(OUT / "06_fallback.png"), full_page=True)
    fbody = page.content()
    check("fallback_message", ("general" in fbody.lower()) and ("Public agency" not in fbody),
          "empty outlook → honest general-prep message, no invented company facts")
    check("fallback_kit_renders", "data process you automated" in fbody,
          "kit still renders as general prep")

    browser.close()

(OUT / "results.json").write_text(json.dumps(results, indent=2))
print(json.dumps(results, indent=2))
if failures:
    print("\nFAILURES:\n" + "\n".join(failures))
    sys.exit(1)
print("\nALL PREP CHECKS PASSED")
