# REQ-058: First-session guidance, nudges and alerts

Date: 2026-10-12
Source: Two of the 6 beta users, relayed by Eduardo, 2026-10-12
Status: Open

## What they said
- User 1 never opened the link. "Did not take the time to enter."
- User 2 found it slow at first, and it wasn't clear where to start looking for a job or what came next.
- Eduardo: "There are no alerts."

## What they actually need
- **Invite:** a reason to click, one that's personal and specific (lifecycle T1/T2, REQ-054).
- **First session:** one obvious next step on every screen until the first fit score. That means a banner with a single action and a highlight on where to click, not a tour to read.
- **Slow first search:** an honest wait that shows progress ("live search, about 40 s, results land one by one").
- **Coming back:** something brings them back without them having to remember. A new-match or interview alert, in the app and by email.

## Constraints
- Nudges are triggered by events already in `core/events.py`.
- They're rendered with the UI kit (`callout`/`notice`), and the highlight uses the Driver.js already in `base.html`.
- Each nudge is shown once per user and can be dismissed. They're capped so they never stack.
- i18n en + es.

## How we'll know it worked
- 60% of new users reach their first fit score on day 0 (REQ-054 activation).
- Users come back within 7 days.

## Related
REQ-054, REQ-010 (onboarding wizard), `docs/growth/lifecycle-emails.md`
