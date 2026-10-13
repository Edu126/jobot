# ADR-084: How we handle user data in the beta

Date: 2026-10-12
Status: Accepted (Eduardo, data and privacy decision pages, 2026-10-12)

## Decision
- **Résumé shape:** we keep today's shape (`parsed_json` and the original file) and document it. ADR-045's structured schema stays on hold.
- **What the AI sees:** before every AI call, code strips the email, phone and personal profile links (LinkedIn, GitHub). The name stays, so writing like cover letters still reads naturally. One function sits at the provider edge, and a test locks it in. LinkedIn and Jobright send whole résumés. We don't, and it costs little.
- **Download:** "Download my data" gives one ZIP with the résumé JSON, the original file, saved jobs as a CSV, and interviews and transcripts as JSON.
- **Retention:** data is kept until the user deletes it. After 12 idle months it's deleted, with a warning email 2 weeks before.
- **One source of truth:** `docs/governance/data_map.yaml` lists every outside service and what it receives. A test fails if the code calls a service the map doesn't list, and the privacy page is written from the map.
- **Privacy wording:** we say "the AI providers we use", not a vendor name.

## Not now
The access log the user can see waits for the shared app (ADR-083). Today Eduardo can open an app's database over SSH, and the app can't log that.

**Build order:** redaction, the data map with its test, and the ZIP export are built (2026-10-12). The 12-month idle deletion ships with the lifecycle emails, because the warning email needs Resend. No beta account can reach 12 months before then.
