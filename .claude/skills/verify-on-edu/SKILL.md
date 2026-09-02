---
name: verify-on-edu
description: "Smoke-test a change against the REAL jobbotv2-edu Fly deploy — the user's staging app — instead of running locally. Use for visual/e2e verification of the Jobot app (Profile, gap map, jobs, tailoring): deploy the current code to jobbotv2-edu, seed deterministic fixture data over SSH, drive it with a headless browser (screenshots + assertions), then restore -edu exactly as found. Triggers: 'verifica en edu', 'testea en fly', 'haz el smoke en -edu', 'deploy y prueba', or any request to confirm a Jobot change works in the real app."
---

# verify-on-edu — smoke a change on the real Fly staging app

The user verifies on **jobbotv2-edu** (their staging Fly app), not locally. This
skill deploys the current code there, seeds deterministic fixtures, drives the
deployed app from a browser, and restores -edu to its prior state. You own -edu
(the user delegated it) — but it **holds their data**, so backup/restore is
mandatory.

Prereqs (all already true on this machine): `fly` authed as the user; the repo
venv has playwright + chromium; `fly.toml` app is `jobbotv2` but we target
`jobbotv2-edu` with `-a`. The DB lives on a volume at `/app/data/jobot.db`.

## The flow

Run from the repo root. `APP=jobbotv2-edu`.

**1. Deploy the current code.**
```bash
fly deploy -a jobbotv2-edu
```
(Uses the repo Dockerfile; `COPY . .` ships the working tree. Smoke scripts are
`.dockerignore`d — they do NOT ride the image; step 3 transfers them at runtime.)

**2. Wait for the new version to be live + healthy.**
```bash
curl -fsS --max-time 15 https://jobbotv2-edu.fly.dev/healthz   # expect 200
fly status -a jobbotv2-edu | grep -i 'passing\|started'
```

**3. Transfer + run the seed** (backs up current résumé, inserts fixtures, sets
them current). The seed script lives beside this SKILL; ship it via base64 (no
sftp/stdin games), then invoke on the machine where the app's deps + code live:
```bash
B64=$(base64 < .claude/skills/verify-on-edu/smoke_edu.py)
fly ssh console -a jobbotv2-edu -C "python3 -c \"import base64,pathlib;pathlib.Path('/tmp/smoke_edu.py').write_bytes(base64.b64decode('$B64'))\""
fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_edu.py seed"     # prints pillars
```

**4. Drive the deployed app from a browser** (the client-side checks: tab switch,
3-pillar layout, no horizontal scroll, popover, ✕ dismiss removes a pill):
```bash
.venv/bin/python .claude/skills/verify-on-edu/drive.py https://jobbotv2-edu.fly.dev /tmp/edu_shots
```
Then LOOK at the screenshots in `/tmp/edu_shots` (SendUserFile the key ones) — a
blank frame is a failed launch, not a pass.

**5. Restore -edu (ALWAYS, even if step 4 failed).**
```bash
fly ssh console -a jobbotv2-edu -C "python3 /tmp/smoke_edu.py restore"  # resets current résumé, deletes smoke rows
```

**6. Report** what rendered + attach screenshots. If the deploy needed manual
patching (new dep, env var, browser install), say so — it means this skill needs
a refresh.

## Adapting the fixture

`smoke_edu.py` seeds a gap-map fixture (résumé + scored jobs + JD-free
classifications with categories/canonicals, incl. a 2-member French cluster). To
smoke a different surface, edit `PARSED` / `JOB_GAPS` / `CLASSIFICATIONS` or add
a new subcommand — keep `seed`/`restore` symmetric so -edu is always left clean.
`smoke_edu.py status` prints the current résumé + pillars without writing.

## Guardrails

- **Never skip restore.** -edu has the user's own résumé/jobs; the marker file
  `/app/data/.smoke_marker` holds the id to reset. `restore` is idempotent.
- Seed writes go through a fresh SQLite connection while the app serves — WAL
  handles it; no machine stop needed for these small writes.
- No API key needed: fixtures include gap classifications under the current
  `gap_map.PROMPT_VERSION`, so `build_gap_map` hits cache, never the LLM.
