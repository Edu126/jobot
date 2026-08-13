"""FastAPI entrypoint for Jobot v2.

Boot with:
    ./run_web.sh
or:
    uvicorn ui_web.main:app --reload

Route map:
    GET  /                      → redirect to /jobs
    GET  /jobs                  → jobs tab (Phase 3)
    GET  /applications          → applications tab (Phase 4)
    GET  /profile               → profile tab (Phase 5)
    GET  /partials/ping         → HTMX smoke-test fragment
    GET  /healthz               → JSON health status

The `core/` package is imported the same way the Streamlit app does — no
duplication. The two UIs share DB, matching, and LLM logic.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Allow `from core...` imports regardless of how uvicorn is launched.
APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import db  # noqa: E402

from .deps import templates  # noqa: E402
from .routes import applications, jobs, journey, profile  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Jobot v2", version="0.2.0", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(APP_ROOT / "static")),
    name="static",
)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/jobs")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Machine-readable status. Handy for the footer link + external checks."""
    counts = db.application_status_counts()
    resumes = db.list_resumes()
    return JSONResponse({
        "ok": True,
        "version": app.version,
        "db": {
            "resumes": len(resumes),
            "applications": sum(counts.values()),
            "status_counts": counts,
        },
    })


@app.get("/partials/ping", response_class=HTMLResponse)
async def ping_partial(request: Request):
    """HTMX smoke-test target. Returns a small HTML badge so the scaffolding
    page can prove the request/swap cycle end-to-end."""
    return templates.TemplateResponse(
        request,
        "partials/ping.html",
        {"now": datetime.utcnow().strftime("%H:%M:%S UTC")},
    )


app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(journey.router)
app.include_router(profile.router)
