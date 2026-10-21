"""Shared fixtures for the server core (M1.2): an app on a temporary data dir, fast orchestrator timings,
a controllable clock, and a scripted capture device that speaks the SPEC 6 protocol."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pulselens.api.main import create_app
from pulselens.config import Settings
from pulselens.orchestrator import OrchestratorConfig

SECRET = "test-secret"
PASSCODE = "test-passcode"


class FakeClock:
    """Monotonic milliseconds that only move when a test says so (plus real time when `follow_real`)."""

    def __init__(self) -> None:
        self.offset = 0.0

    def advance(self, ms: float) -> None:
        self.offset += ms

    def __call__(self) -> float:
        import time

        return time.monotonic() * 1000 + self.offset


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


FAST = OrchestratorConfig(
    stage_timeout_s=5.0, gap_ms=(0, 5), release_jitter_ms=(0, 0), duration_ms=40, expires_in_ms=300, ack_grace_ms=2000
)


@pytest.fixture
def make_client(tmp_path: Path, clock: FakeClock) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def make(**overrides: Any) -> TestClient:
        settings = Settings(pulse_hmac_secret=SECRET, console_passcode=PASSCODE, team_codes=("P01",))
        app = create_app(
            data_dir=overrides.pop("data_dir", tmp_path / "data"),
            settings=settings,
            orchestrator=overrides.pop("orchestrator", FAST),
            clock=overrides.pop("clock", clock),
            **overrides,
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def create_session(client: TestClient, **body: Any) -> dict:
    r = client.post("/api/sessions", json={"mode": "superset", "product": "lab", **body})
    assert r.status_code == 200, r.text
    return r.json()


@dataclass
class CaptureRun:
    """What a scripted capture device saw during one session."""

    received: list[dict] = field(default_factory=list)
    acks_sent: list[dict] = field(default_factory=list)


def default_ack(pulse: dict) -> dict:
    """An on-time, well-formed ack: painted 30 ms after received, ended after the duration."""
    received = 1000.0
    duration = pulse["params"].get("duration_ms", 40)
    return {
        "type": "ack",
        "pulse_id": pulse["pulse_id"],
        "sig": pulse["sig"],
        "received": received,
        "applied": received + 15,
        "painted": received + 30,
        "ended": received + 30 + duration,
        "ok": True,
        "error": None,
        "shown": {"neutral": [188, 188, 188], "rgb": [250, 163, 185]},
    }


def run_capture(
    ws, *, ack: Callable[[dict], dict | list[dict] | None] = default_ack, on_pulse: Callable[[dict], None] | None = None
) -> CaptureRun:
    """Plays the capture device until `done`: finishes client stages and acks every pulse."""
    run = CaptureRun()
    while True:
        msg = ws.receive_json()
        run.received.append(msg)
        if msg["type"] == "stage" and msg["stage"] in ("camera", "coach"):
            ws.send_json({"type": "stage.done", "stage": msg["stage"], "data": {"rounds": []}})
        elif msg["type"] == "pulse":
            if on_pulse:
                on_pulse(msg)
            replies = ack(msg)
            for reply in replies if isinstance(replies, list) else [replies] if replies else []:
                ws.send_json(reply)
                run.acks_sent.append(reply)
        elif msg["type"] == "done":
            return run
