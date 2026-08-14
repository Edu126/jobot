# Deploying Jobot to Fly.io (per-user testing)

A short walkthrough for putting Jobot v0.5-dev on the public internet via Fly.io's free tier. Uses **one-app-per-user** as poor-man's multi-tenancy while proper auth (Notion doc "Jobot — Multi-user Architecture") is on the roadmap. Each user gets their own isolated app + volume + URL.

> **TL;DR — auto-deploy on push**: after the one-time setup in [Auto-deploy](#auto-deploy-on-push-to-main), every `git push origin main` deploys all 3 per-user apps in parallel via GitHub Actions.

---

## Prerequisites

1. Install the Fly CLI:
   ```bash
   brew install flyctl
   ```
2. Sign up (or log in) — free, no credit card needed to start:
   ```bash
   fly auth signup   # first time
   fly auth login    # if you already have an account
   ```
3. Make sure your `.env` at the repo root has `GOOGLE_API_KEY=…` filled in.

---

## First deploy

From the repo root:

```bash
bash scripts/deploy-fly.sh
```

The script:
- Checks the CLI is installed and you're logged in
- Runs `fly launch --no-deploy` if this is the first time (registers the app name)
- Creates a 1GB persistent volume `jobot_data` for the SQLite DB (idempotent)
- Reads `GOOGLE_API_KEY` from your local `.env` and pushes it as a Fly secret
- Builds the Docker image and deploys it
- Prints the URL: `https://jobot-testing.fly.dev`

> **Name collision?** `jobot-testing` may already be claimed. If `fly launch` prompts you for another name, accept the suggestion and then edit the `app = "..."` line in `fly.toml` to match, and re-run the script.

Expect 2-4 minutes on the first build (pip install is the slow part). Subsequent deploys reuse the dep layer and take 30-60s.

---

## Ongoing deploys

After code changes:

```bash
fly deploy
```

That's it. The image rebuilds, the machine rolls, health checks gate the cutover.

---

## Common ops

| Task | Command |
| --- | --- |
| Tail logs | `fly logs` |
| App status + machine list | `fly status` |
| SSH into the running machine | `fly ssh console` |
| Pull DB locally to inspect | `fly ssh sftp shell` → `get /app/data/jobot.db` |
| List past releases | `fly releases` |
| Roll back to a prior release | `fly deploy --image <image_ref_from_releases>` |
| Restart the machine | `fly machine restart` |
| See/edit secrets | `fly secrets list` / `fly secrets set KEY=value` |

### Inspecting the SQLite DB

```bash
fly ssh sftp shell
> get /app/data/jobot.db ./jobot-remote.db
> exit
sqlite3 jobot-remote.db '.tables'
```

Or directly on the machine:

```bash
fly ssh console
$ sqlite3 /app/data/jobot.db 'SELECT COUNT(*) FROM jobs;'
```

---

## Cost — what's free, when you start paying

Fly.io's free allowance covers:
- **3× shared-cpu-1x machines** (256MB each)
- **3GB persistent volume storage**
- **160GB outbound bandwidth / month**

Jobot's config uses:
- **1 machine, 512MB RAM** — the extra 256MB above the free tier costs roughly $1.50/month (pandas + Gemini response buffering benefit from the headroom). Drop to 256MB in `fly.toml` if you want to stay strictly free — watch for OOM restarts.
- **1GB volume** — well under the 3GB allowance.
- **scale-to-zero** (`min_machines_running = 0`) — the VM sleeps when idle, so most days you consume zero machine-hours.

You'll start paying if you:
- Bump memory > 256MB (small $/mo)
- Add more machines / regions
- Exceed 160GB egress (Jobot won't — pages are tiny)
- Grow the volume beyond 3GB total

---

## Heads-up: LinkedIn / Indeed may block hosted IPs faster

jobspy scrapes LinkedIn and Indeed from the container's outbound IP. Hosted / datacenter IP ranges (Fly, AWS, GCP, etc.) get flagged by these sites' anti-scraping systems **much more aggressively** than residential IPs like Eduardo's home connection.

Practical impact:
- Searches may return empty results, 403s, or CAPTCHA walls that never resolved when running locally
- Watch for the new `SEARCH_BLOCKED` timeline events (added in commit `ee4e802`) on the Journey tab — they'll fire when a provider returns nothing / errors out
- If it becomes chronic: run the app locally for real searches, and use Fly only for UI / demo / lightweight targeted analysis (which uses direct URL fetches, not board search)

Nothing here changes the Gemini calls or the local DB — those work identically remote vs local.

---

## Uninstalling

```bash
fly apps destroy jobot-testing
fly volumes list                  # if the volume lingers
fly volumes destroy <volume-id>
```

---

## Auto-deploy on push to main

The workflow at `.github/workflows/deploy-fly.yml` deploys all per-user apps in parallel every time `main` gets a new commit (or when triggered manually from the Actions tab). Setup is one-time.

### 1. Create an org-wide Fly deploy token

```bash
fly tokens create org
```

Copy the whole `FlyV1 fm2_...` string it prints. This token can deploy any app in your Fly org.

### 2. Add the token as a GitHub secret

```bash
gh secret set FLY_API_TOKEN --body="FlyV1 fm2_...paste-your-token-here..."
```

Or via the browser: <https://github.com/Edu126/jobot/settings/secrets/actions> → **New repository secret** → name `FLY_API_TOKEN`, value = pasted token.

### 3. Push to main → auto-deploy

Every subsequent push runs `fly deploy` for all 3 apps in parallel. Watch it live at <https://github.com/Edu126/jobot/actions>.

To trigger manually (e.g. after adding a new secret):

```bash
gh workflow run "Deploy to Fly.io"
```

### 4. Adding a new per-user app to the matrix

When you `bash scripts/deploy-fly.sh alicia` and create a new app, add it to the workflow so auto-deploy covers it:

```yaml
# in .github/workflows/deploy-fly.yml
matrix:
  app:
    - jobbotv2
    - jobbotv2-melissa
    - jobbotv2-hermana
    - jobbotv2-alicia   # <-- add here
```

Commit + push. Next deploy includes the new app.

### Skipping deploy for doc-only commits

The workflow ignores changes to `*.md`, `docs/**`, `.gitignore`, `PROJECT.md`, `screenshots/**`, and `.claude/**` — so a README tweak doesn't burn CI minutes or a Fly rollout on all 3 apps.
