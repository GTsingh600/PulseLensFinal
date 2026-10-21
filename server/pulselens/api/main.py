"""FastAPI app factory. Routers: sessions and pairing (REST), the session WebSocket. Lab and Demo routes come later.

No CORS middleware on purpose: both sites reach the API through their own origin (Vite proxy / tunnel), so the
browser's same-origin rule already limits callers (SPEC 17).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from pulselens import __version__
from pulselens.api import sessions, ws
from pulselens.config import DATA_DIR, Settings, config_hash, get_settings, load_config
from pulselens.hub import Hub
from pulselens.orchestrator import OrchestratorConfig
from pulselens.store import SessionStore

log = logging.getLogger("pulselens")


class Health(BaseModel):
    status: str
    version: str
    config_hash: str


def create_app(
    *,
    data_dir: Path | None = None,
    settings: Settings | None = None,
    orchestrator: OrchestratorConfig | None = None,
    clock: Callable[[], float] | None = None,
) -> FastAPI:
    """`clock` is monotonic milliseconds (pulse deadlines, pair-code expiry); tests pass a controllable one."""
    config = load_config()
    settings = settings or get_settings()
    hub = Hub(
        store=SessionStore(data_dir or DATA_DIR),
        settings=settings,
        orchestrator=orchestrator or OrchestratorConfig.from_config(),
        clock=clock or (lambda: time.monotonic() * 1000),
        pair_ttl_ms=config["demo"]["pair_code_ttl_min"] * 60_000,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.uses_placeholders:
            log.warning("PULSE_HMAC_SECRET or CONSOLE_PASSCODE is still 'change-me'; set real values in .env")
        yield
        await hub.shutdown()

    app = FastAPI(title="PulseLens", version=__version__, lifespan=lifespan)
    app.state.hub = hub

    @app.get("/api/health")
    def health() -> Health:
        return Health(status="ok", version=__version__, config_hash=config_hash()[:12])

    app.include_router(sessions.router)
    app.include_router(ws.router)
    return app


app = create_app()
