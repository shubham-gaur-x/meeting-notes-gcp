"""FastAPI service — Cloud Run, scales to zero.

Entrypoint only: every route is a thin wrapper over the package (CLAUDE.md).

**Zero APScheduler.** v5's `main.py` carried 17 scheduler references; in v6
scheduling is Cloud Scheduler triggering Cloud Run Jobs, and a test asserts
the string appears nowhere under `api/`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from api.routers import graph, insights, memory, review, webhooks
from meeting_notes.config import get_settings
from meeting_notes.utils import configure_logging

log = structlog.get_logger()

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure_logging()
    settings = get_settings()
    log.info("api.startup", backend=settings.llm_backend, memgraph=settings.memgraph_host)
    yield
    # Cloud Run recycles instances freely; leaving the Bolt driver open holds
    # server-side sessions after the instance is gone.
    from meeting_notes.graph_client import close_driver

    await close_driver()
    log.info("api.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="meeting-notes-gcp",
        description="Meeting memory graph — query layer",
        version="0.1.0",
        lifespan=lifespan,
    )
    for router in (graph.router, review.router, insights.router, memory.router, webhooks.router):
        app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness plus a real Memgraph round-trip.

        Reports `degraded` rather than failing: Cloud Run should keep the
        instance while a dependency is down, so the cause is visible instead of
        the service disappearing.
        """
        settings = get_settings()
        graph_ok = False
        try:
            from meeting_notes.graph_client import get_driver

            driver = get_driver()
            async with driver.session() as session:
                result = await session.run("RETURN 1 AS ok")
                graph_ok = any([r async for r in result])
        except Exception as exc:  # noqa: BLE001
            log.warning("health.memgraph_unreachable", error=str(exc))

        return {
            "status": "ok" if graph_ok else "degraded",
            "memgraph": graph_ok,
            "llm_backend": settings.llm_backend,
        }

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard() -> HTMLResponse:
        return HTMLResponse((STATIC / "dashboard.html").read_text(encoding="utf-8"))

    return app


app = create_app()
