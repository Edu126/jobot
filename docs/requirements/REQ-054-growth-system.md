# REQ-054: A growth system for the Reddit beta (acquire, activate, retain, learn)

Date: 2026-10-12
Source: Eduardo, CTO review follow-up
Status: Open

## What they asked for
"It takes something more than that, I think you are planning this as if we
were college students… I used to work at Facebook. Not something super
production-ready, but with the right tools to make it work, like the copies
for the emails etc. We can use Resend. You help be the centralizer… some
skill so we have a growth/marketing person."

## What they actually need
A small but real growth loop around the beta. Every stage gets a metric, an
owner (usually the growth skill, with Eduardo approving), and a tool. That
way we learn why testers stay or leave, not just how many came.

### Metrics
- **North star (Phase 1, product vision):** interview rate per application.
  Beta proxy: prepared applications (tailored + downloaded, ADR-044) per
  active tester per week, plus self-declared interviews (an Interview created in Prep).
- **Activation ("aha"):** on day 0, the tester uploads a résumé, runs a
  search and opens at least one fit explanation. Target: 60% of approved testers.
- **Retention:** active on 2 or more distinct days in week 2 (ADR-039
  intention). Read by weekly cohort.

### Funnel and events
- **Funnel:** waitlist joined → approved → invite sent → first sign-in →
  activated → week-2 active → interview declared.
- **New events:** `waitlist.joined`, `auth.invited`, `auth.first_login`,
  `activation.reached`, plus Resend webhooks (delivered, opened, clicked,
  bounced, unsubscribed).

### Lifecycle email (Resend)
- Triggers are defined in `docs/growth/lifecycle-emails.md`.
- Caps: at most 2 marketing emails a week, never on a day the person was
  active, and one-click unsubscribe.
- Transactional emails (invite, sign-in) are separate from marketing.

### Compliance
- **Commercial emails (CASL, Canada):** express consent at waitlist sign-up,
  sender identified, unsubscribe honoured within 10 business days.
- **Personal data (PIPEDA):** a privacy page covering what is stored, where
  (Supabase region), what goes to Google Gemini, and deletion (Delete all already exists).
- **Email sending domain:** SPF, DKIM and DMARC on our own domain.

### Feedback
- The existing widget, plus a 2-question check-in on day 7.
- 15-minute calls with 5 testers a week.
- Every theme becomes a REQ (the existing loop).
- "You asked, we shipped" emails close the loop.

### Cadence
A weekly growth review every Monday, prepared by the growth skill:
- funnel and cohort numbers,
- the top 3 feedback themes,
- one decision for the week.

### Tools
- Supabase, Resend and Turnstile.
- The fleet pull (ADR-035) extended to the funnel, rendered as a
  Claude artifact dashboard.
- No third-party analytics (overview.md boundary).

### Copy rules
- Claims must be provable. Jobot pulls from the same boards as LinkedIn,
  so never write "better/faster than LinkedIn".
- Speed copy is honest: the first search runs live; repeat searches are
  served from cache (ADR-083 makes the cache shared).

### What we're not doing
A/B tests at 20 users don't reach significance. Qualitative feedback wins until about 200 users.

## How we'll know it worked
At the end of the beta, one view answers: of the approved testers, how many
activated, how many came back in week 2, and why the rest didn't. It
answers that with quotes, not guesses.

## Related
ADR-082, ADR-083, ADR-044, ADR-039, ADR-035, GOV-003, REQ-055
