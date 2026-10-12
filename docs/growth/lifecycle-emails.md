# Lifecycle emails: drafts for review (REQ-054)

Status: **DRAFT.** Nothing is sent until Eduardo approves the copy.
Sender: "Eduardo at Jobot" <eduardo@{domain}>, sent through Resend.

Voice: one person writing to one person. Short sentences, no hype, no em
dashes, one link per email. Spanish (`es`) is wired once English is
approved.

**Global rules**
- Cap: 2 marketing emails a week. Never on a day the person was active.
- Every marketing email has a one-click unsubscribe (CASL).
- Transactional emails (T) need no consent. Marketing emails (M) need the
  consent box ticked on the waitlist form.

---

## T1 · Invite (on approval)
**Trigger:** Eduardo approves a waitlist entry and the app has been created.
**Subject:** I read your sign-up. You're in.
**Preview:** One click to set up your account.

Hi {first_name},

I approve every Jobot tester by hand, because I want people who'll tell me
the truth about it. You're one of them.

Jobot finds jobs that fit your real experience, explains why, and helps you
practise the interview out loud before it happens.

[Set up my account]

You can sign in with Google or with a code sent to this email. The link
works for 7 days.

Eduardo

## T2 · Welcome (first sign-in)
**Trigger:** `auth.first_login`
**Subject:** Your first honest fit score is 10 minutes away
**Preview:** Your résumé, one search, one fit explanation.

Hi {first_name},

You're in. Here's the quickest way to see if Jobot is useful to you:

1. Upload your résumé (2 minutes).
2. Search for one role you'd actually apply to. The first search runs live
   on the job boards, so it takes about a minute.
3. Open one job and read why it fits, and what's missing.

[Open Jobot]

If something feels off, reply to this email. I read every one.

Eduardo

## M1 · Day 1, no résumé yet
**Trigger:** 24 hours after first sign-in and no `resume.uploaded`.
**Skip if:** they were active today.
**Subject:** The one step that makes Jobot work
**Preview:** Without a résumé it can't tell you what fits.

Hi {first_name},

Jobot needs your résumé to judge fit. Without it, every job looks the same.

It stays in your own private space. We never share it or sell it. [How we handle your data]

[Upload my résumé]

Eduardo

## M2 · Day 3, activated but hasn't returned
**Trigger:** `activation.reached` and no activity for 72 hours.
**Skip if:** no job scored at least 60 (better to say nothing than send a weak match).
**Subject:** Your best match this week: {top_job_title}, {top_score}
**Preview:** {n_matches} things fit, {n_gaps} gap. Here's why.

Hi {first_name},

Of everything you searched, this one fits you best:

**{top_job_title}** at {top_company}, fit {top_score}
- Fits: {match_1}
- Fits: {match_2}
- Gap: {gap_1}

[See why it fits]

Eduardo

*Build note: filled from the tester's own cached scores. No new LLM call, no invented reasons.*

## M3 · Interview created
**Trigger:** an Interview is created in Prep **and** has a real company and a real date.
**Skip if:** the user marked the interview as "just testing" (needs a toggle on the Interview; see Build notes).
**Subject:** {company}: 3 questions to expect
**Preview:** Practise them out loud before {interview_day}.

Hi {first_name},

You've got an interview with {company}. That's the hard part done.

From the brief Jobot built, these are likely to come up:
1. {question_1}
2. {question_2}
3. {question_3}

[Practise these out loud]

Headphones and a quiet room help. Good luck.
Eduardo

*Build notes (Eduardo: "make sure this is real, and let the user remove it, it could be they were just testing"):*
- *Questions come only from the Interview's existing prep (P2). If fewer than 3 exist, don't send.*
- *Add "This is just practice, not a real interview" on the Interview. It suppresses M3 and M7 and keeps it out of the outcome KPI.*

## M4 · Day 7 check-in
**Trigger:** 7 days after first sign-in.
**Subject:** Two questions about your first week
**Preview:** 30 seconds, and it really helps.

Hi {first_name},

A week in. Two quick questions:

1. What's the one thing Jobot did that was useful?
2. What's the one thing that got in your way?

Reply here, or answer in the app. If you'd rather talk, here's 15 minutes on
my calendar: [Book a call]

Eduardo

## M5 · Day 14, gone quiet
**Trigger:** no activity for 10 days.
**Subject:** Did you get the job?
**Preview:** One tap either way.

Hi {first_name},

You haven't been back in a while. Maybe that's good news.

[Yes, I got it 🎉]   [Still looking]

If you're still looking and Jobot missed the mark, reply and tell me why.
One line is enough. If you'd rather not hear from me, [unsubscribe].

Eduardo

*Build note: each button records an outcome event (the north-star signal), then shows a thank-you page.*

## M6 · You asked, we shipped
**Trigger:** manual, when a REQ that came from this tester ships.
**Subject:** You asked for {thing}. It's live.
**Preview:** Thanks for telling me.

Hi {first_name},

On {date} you told me {their words}. Today it's live: {one line on what changed}.

[Try it]

Thanks for taking the time. This is how Jobot gets better.

Eduardo

## M7 · Your job market this week
**Trigger:** every Monday, if there are 3 or more new matches or the top gap changed.
**Skip if:** they were active in the last 24 hours, or they declared "got the job".
**Subject:** {n_new} new matches, and your top gap this week
**Preview:** {top_new_title} leads at {top_new_score}.

Hi {first_name},

This week in your search:
- **{n_new} new matches.** The best: {top_new_title} at {top_new_company} ({top_new_score}).
- **Your top gap:** {top_gap}, seen in {gap_count} of your last {job_count} jobs.

[See this week's matches]

Eduardo

*Build note: computed by code from cached scores and the gap map. No LLM call. Counts as one of the 2 weekly marketing emails.*
