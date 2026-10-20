"""FastAPI app. Routers for sessions, ws, lab and demo (SPEC 6) are mounted here as they are built."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from pulselens import __version__
from pulselens.config import config_hash, get_settings, load_config

log = logging.getLogger("pulselens")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    load_config()  # fail fast on a broken config.yaml
    if get_settings().uses_placeholders:
        log.warning("PULSE_HMAC_SECRET or CONSOLE_PASSCODE is still 'change-me'; set real values in .env")
    yield


app = FastAPI(title="PulseLens", version=__version__, lifespan=lifespan)


class Health(BaseModel):
    status: str
    version: str
    config_hash: str


@app.get("/api/health")
def health() -> Health:
    return Health(status="ok", version=__version__, config_hash=config_hash()[:12])
