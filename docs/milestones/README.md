# Jobot milestones — the visual story

A running log of the moments worth telling: what the app looked like, what
changed, and why it mattered. Raw material for posts, the portfolio/project
page on our résumés, and later Jobot's own story page.

**Not a changelog.** The changelog is git + ADRs. A milestone is a moment a
person would care about: a first, a before/after, a hard problem cracked, a
user reaction.

## How we capture
1. **Spot it.** Claude flags "📸 milestone?" when something visible or
   meaningful lands. Eduardo can also call one anytime.
2. **Capture it.** Eduardo takes the screenshot or recording (Claude doesn't
   take screenshots, per our way of working). Raw files stay private.
3. **File it.** Claude crops it to the app only (no tabs, bookmarks or
   desktop), saves it under `assets/YYYY-MM-DD-<slug>.png`, and writes the
   entry: the story, the before/after, links to the ADR/REQ/commit, and a
   short post draft (EN + ES).
4. **Before posting:** check that no real user data shows (names, companies
   from someone else's search, emails). Our own -edu data is fine to show.
   Blur if unsure.

## Index
| Date | Milestone | Kind | Visual |
|---|---|---|---|
| 2026-10-01 | [The voice lab — tuning an AI interviewer by ear](2026-10-01-voice-lab.md) | First · experiment | ✅ |
| 2026-10-01 | [Honest feedback — "Solid" for junk answers → a 0–100 you can audit](2026-10-01-honest-session-score.md) | Before/after | before ✅ · after 📸 pending |

## Entry template
```md
# <Headline a stranger would understand>
Date · Kind (first / before-after / problem cracked / user moment) · Links (ADR, REQ, commit)

## The moment          — one paragraph, plain language
## Why it matters      — the problem underneath
## Visuals             — images, with a one-line caption each
## Post draft          — EN (≤ 600 chars) + ES
```
