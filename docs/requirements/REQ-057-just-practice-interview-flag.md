# REQ-057: Mark an interview as "just practice"

Date: 2026-10-12
Source: Eduardo (film and email review, next-steps page, 2026-10-12)
Status: Open. It has to ship before the lifecycle emails go live.

## What they asked for
Being able to say "this is just practice, not a real interview" on an Interview.

## What they actually need
Emails about a specific interview must never assume there is a real one:
M3 "{company}: 3 questions to expect" and the interview lines in M7.
Practice runs also shouldn't count toward the interview or outcome KPIs (REQ-054).

## Constraints
- One boolean on the interview row (`is_practice`, default false). Legacy rows read it as false.
- A single toggle on the Interview page, built from the UI kit, with no new screen.
- The email sender and the KPIs read the flag. The prep pipeline ignores it.
- Delete-all keeps working (`tests/test_delete_all.py`).

## How we'll know it worked
Zero M3 emails are sent for interviews marked as practice, checked against the email log.

## Related
REQ-054, `docs/growth/lifecycle-emails.md` (M3, M7)
