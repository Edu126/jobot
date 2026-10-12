# Landing product film: script v2 (REQ-055)

Status: **v2, built from Eduardo's review answers (2026-10-12).** The
`motion` skill builds scenes from this file.

**Concept: one application, step by step.** We follow Sam through a
single application. There is no week-long clock: everyone's process
moves at its own pace. The point is that Jobot is there at each step.
The on-screen step label replaces the clock: *Find → Understand →
Tell → Practise → Walk in ready.*

**Constraint (Eduardo):** every product screen must look like the current
beta. No invented screens. The motion is new; the UI isn't.

**Fixture candidate (invented):** Sam Rivera, project coordinator, 6 years.
Jobs at invented companies: Northline Construction, Harbor Health, Lumen
Transit. Never real users.

| # | Step | What moves | On-screen copy | ~Time |
|---|---|---|---|---|
| 0 | **The blank page** | An empty résumé, a blinking cursor: the moment everyone dreads. Then a counter rolls down: Applications 147 … 61 … 12 … 5. The headline types into the blank space. | **The support team behind your job search.** Fewer applications. The right ones. And time for the things that matter. [Join the beta] | 6 s, then still |
| 1 | **Find · Understand** | A posting slides in. A split screen: the left side is the posting's words, the right side is Jobot's plain reading of them, line by line. The fit ring fills to 78. | "Fast-paced environment" → You'll juggle 5+ projects. You've done 14. / "PMP preferred" → You don't have it. Not a blocker here. **Know what a job really asks for.** | 7 s |
| 2 | **Understand, across jobs** | The camera pulls back over about 40 scored postings. Gap tokens fall from each into 3 piles. The counters tick up live, and a measuring bar fills next to each pile, so it's clear the gap is being *measured*, not guessed. | Scheduling software · 31 of 40 jobs / Budget ownership · 22 of 40 / Site safety · 9 of 40. **Know what to learn first.** | 7 s |
| 3 | **Tell** | Sam's résumé is seen through a recruiter's eyes. A highlighter sweeps it in 6 seconds and catches little. Then the tailored version: the highlighter lights up the words that now match the posting's and the company's language. | **Your real experience, in the language they're looking for.** | 6 s |
| 4 | **Practise** | An incoming-call screen, "Interview practice · Maya". Answer → the real beta practice screen: the voice wave, captions, then the feedback. Tap for sound (optional; the page works muted). | **Rehearse the interview out loud, before it happens.** | 7 s |
| 5 | **Walk in ready** | Still. An open letter in plain type, signed by Eduardo. No icons. | See below | still |

## Scene 5 · The open letter
> Job tools work for the people hiring. I'm building one that works for you.
> Everyone's search is different, so Jobot doesn't push you to apply to
> more. It helps you find the few that fit, tell your real story, and walk
> in prepared. It's early, it's honest, and I read every message.
> Eduardo

Under the letter: [Join the beta]. Then the privacy line: "Your data lives in its own private space. We never sell it. Delete everything in one click." [How we handle your data]

## Product follow-ups the film surfaced
- **Incoming-call animation before live practice** (Eduardo: "something we should replicate"). It goes into the product as well as the film. Needs its own REQ.
- **Scene 4:** must match the current beta practice screen. The motion skill recreates it from `ui_web/templates/`, not from imagination.
