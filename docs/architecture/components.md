# Component Diagram

Last updated: 2026-08-21

```mermaid
flowchart TB
    subgraph Browser
        UI[HTMX + Alpine UI<br/>Jinja2-rendered]
        Widget[Feedback widget<br/>File upload]
        Settings[Floating settings panel]
    end

    subgraph FlyApp["Fly.io app (one per user)"]
        Router[FastAPI router<br/>ui_web/main.py]
        Mid[Middleware<br/>IdentityMiddleware<br/>SlowAPI rate-limit]
        Routes[Routes:<br/>jobs / journey / profile<br/>admin/pulse / feedback]

        subgraph Core
            Jobs[core/jobs/<br/>scrapers + URL import<br/>+ background tasks]
            Match[core/matching/<br/>semantic_score.py<br/>batched scoring]
            LLM[core/llm/<br/>GeminiClient<br/>fallback chain]
            Resume[core/resume/<br/>parse + regenerate<br/>+ ATS checks]
            BI[core/bi/pulse.py<br/>weekly report]
            Events[core/events.py<br/>append-only log]
        end

        DB[(SQLite<br/>data/jobot.db<br/>+ Fly volume)]
        FS[(data/feedback/*.png/jpg<br/>on the same volume)]
    end

    subgraph External
        Gemini[Google Gemini API<br/>3-model fallback chain]
        JobBoards[Job boards<br/>LinkedIn / Indeed / Google Jobs<br/>via python-jobspy]
        GH[GitHub Actions<br/>weekly pulse cron<br/>+ deploy on push]
    end

    UI --> Router
    Widget --> Router
    Settings --> Router
    Router --> Mid
    Mid --> Routes
    Routes --> Jobs
    Routes --> Match
    Routes --> Resume
    Routes --> BI
    Routes --> Events
    Routes --> DB
    Jobs --> JobBoards
    Jobs --> LLM
    Match --> LLM
    Resume --> LLM
    BI --> LLM
    LLM --> Gemini
    Routes --> FS
    GH -.->|scheduled ssh| Router
    Events --> DB
    BI --> DB
```

## Notes

- **One instance of the whole diagram per user** during POC — the
  outer `Fly.io app` box is replicated across 3 apps today
  (`jobbotv2`, `jobbotv2-hermana`, `jobbotv2-melissa`). See ADR-001.
- **Middleware order matters.** IdentityMiddleware runs FIRST so
  downstream Gemini calls see the right identity for per-day cap
  accounting. SlowAPI's SQLite-backed store persists rate-limit
  counters across Fly's `auto_stop_machines` cycling.
- **Gemini boundary is provider-agnostic by design.** `GeminiClient`
  exposes `generate_json(prompt) -> dict`. The multi-provider
  migration (ADR-004 consequence) will swap the client, not the
  callers.
- **Job scraping is synchronous during a search request** but
  batched inside `core/matching/semantic_score.py` (6 jobs per
  Gemini call, sequential — chosen deliberately to avoid rate
  limits + "lost in the middle" degradation).
- **Feedback screenshots** are written to `data/feedback/` on the
  Fly volume alongside `jobot.db`. File extension follows the
  uploaded mime (png / jpg / webp / gif); the DB stores only the
  path.
- **The pulse cron runs from GH Actions**, not an in-app scheduler.
  Wakes the (auto-stopped) Fly machine via `/healthz` first, then
  runs `python -m core.bi.pulse` over SSH.
- **No third-party analytics or telemetry.** Only the signal tables
  in the local SQLite feed the pulse report.

---

## The live prep call (REQ-041 / ADR-047) — planned, flag-gated

> Added 2026-09-16. The main diagram above predates Prep entirely and is
> **stale** (no `core/prep/`, no Tavily hop) — backfilling it is its own pass.
> This sub-diagram is drawn separately because the live call introduces the one
> genuinely new *shape* in jobot's architecture: **an edge from the browser
> straight to an external provider, bypassing our server.**

```mermaid
flowchart LR
    subgraph Browser
        Page[Prep call page<br/>Alpine + CDN ESM<br/>@google/genai]
        Mic[Mic capture<br/>16kHz PCM]
        Spk[Playback 24kHz<br/>+ AnalyserNode]
        Avatar[Avatar mouth<br/>RMS envelope, ~60fps]
    end

    subgraph FlyApp["Fly.io app (one per user)"]
        Mint["POST /prep/{id}/call/token<br/>caps + ownership + BI<br/>builds system instruction"]
        Post["POST /prep/{id}/call/debrief<br/>transcript in"]
        Kit[(prep_kits<br/>the agenda)]
        Sess[(prep_sessions<br/>JD, resume_hash, fit)]
        Out[(company_outlook)]
        Debrief[core/prep/debrief.py<br/>generate_json, cheap chain]
    end

    subgraph External
        Live[Gemini Live API<br/>WebSocket, audio-only]
        Gem[Gemini generate_json<br/>DEFAULT_MODEL_CHAIN]
    end

    Page -->|1. ask for token| Mint
    Kit --> Mint
    Sess --> Mint
    Out --> Mint
    Mint -->|2. ephemeral token + config| Page
    Mic --> Page
    Page <==>|3. AUDIO — never touches our server| Live
    Live --> Spk
    Spk --> Avatar
    Page -->|4. transcript at end| Post
    Post --> Debrief
    Debrief --> Gem
    Post --> Sess
```

Read the thick edge (3) as the whole point: our machine mints a short-lived
token and steps out of the media path. It is sized for HTML fragments, not for
carrying five minutes of PCM.

Three properties fall out of that shape:

- **The token endpoint is the only enforcement point that exists.** Caps,
  ownership and BI logging live there, because nothing after it is ours to
  police (ADR-051).
- **Grounding is front-loaded, not supervised.** The agenda goes into the system
  instruction before the socket opens (ADR-048); we cannot inspect turns.
- **The avatar is a local rendering of audio already in the browser's graph** —
  zero tokens, zero server CPU, and the reason we stay in the 15-minute
  audio-only lane instead of the 2-minute video one (ADR-050).
