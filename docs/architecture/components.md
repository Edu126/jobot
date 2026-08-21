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
