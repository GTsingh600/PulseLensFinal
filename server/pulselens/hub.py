"""Live sessions: WebSocket connections by role, the capture device, pulse bookkeeping (SPEC 5, 6, 17).

Roles on /ws/session/{id}:
- customer: the capture device in the Demo. Receives only stage, prompt, pulse and done messages, and every one
  passes `assert_customer_safe` on the way out: no scores, check names or families can reach a customer.
- lab: the capture device in the Lab. Receives capture messages and every event.
- presenter: a viewer. Receives every event; on connect it first gets the events from `from` (default 0).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import WebSocket
from pydantic import BaseModel, ValidationError

from pulselens.config import Settings
from pulselens.events import EventBus
from pulselens.models import EventMessage, PulseAck, SessionCreate, SessionCreated, StageDone
from pulselens.pairing import PairingRegistry
from pulselens.pulses import same_signature
from pulselens.store import SessionStore

Role = Literal["customer", "lab", "presenter"]
ROLES: tuple[Role, ...] = ("customer", "lab", "presenter")
CAPTURE_ROLES = ("customer", "lab")

CUSTOMER_TYPES = frozenset({"stage", "prompt", "pulse", "done"})
CUSTOMER_FORBIDDEN_KEYS = frozenset(
    {
        "score",
        "scores",
        "check_id",
        "family",
        "families",
        "failed_families",
        "threshold",
        "threshold_source",
        "band",
        "features",
        "coverage",
        "route",
        "reasons",
        "explainer",
        "plot",
        "decision",
    }
)


class CustomerPayloadError(ValueError):
    pass


def assert_customer_safe(msg: dict[str, Any]) -> None:
    """Raises unless `msg` is a customer message type with no scoring key at any depth (SPEC 6, 17)."""
    if msg.get("type") not in CUSTOMER_TYPES:
        raise CustomerPayloadError(f"message type {msg.get('type')!r} never goes to a customer")

    def walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in CUSTOMER_FORBIDDEN_KEYS:
                    raise CustomerPayloadError(f"customer payload carries {path}{k}")
                walk(v, f"{path}{k}.")
        elif isinstance(obj, list):
            for v in obj:
                walk(v, path)

    walk(msg, "")


class Connection:
    """One WebSocket; messages go out in order through a queue, so senders never block the event loop."""

    def __init__(self, ws: WebSocket, role: Role) -> None:
        self.ws = ws
        self.role = role
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.unsubscribe: Callable[[], None] = lambda: None

    def send(self, msg: dict[str, Any]) -> None:
        if self.role == "customer":
            assert_customer_safe(msg)
        self._queue.put_nowait(msg)

    async def pump(self) -> None:
        while (msg := await self._queue.get()) is not None:
            await self.ws.send_json(msg)

    def close(self) -> None:
        self.unsubscribe()
        self._queue.put_nowait(None)


@dataclass
class PulseState:
    pulse_id: str
    kind: str
    source: str
    params: dict[str, Any]
    sig: str
    released: float  # server monotonic ms
    deadline: float
    acked: bool = False
    done: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())


class SessionRuntime:
    def __init__(self, hub: Hub, session_id: str) -> None:
        self.hub = hub
        self.session_id = session_id
        self.meta = hub.store.meta(session_id)
        self.bus = EventBus(hub.store.bundle_path(session_id) / "events.jsonl")
        self.capture: Connection | None = None
        self.pulses: dict[str, PulseState] = {}
        self.stage_done: dict[str, asyncio.Future] = {}
        self.next_stage = asyncio.Event()
        self.waiting_for: str | None = None  # step mode: the stage that /next would release
        self.rng = random.Random()
        self.orchestrator: asyncio.Task | None = None

    @property
    def mode(self) -> str:
        return str(self.meta.get("mode"))

    # --- connections ---

    def attach(self, conn: Connection, from_seq: int | None) -> bool:
        """False when a second capture device tries to join a session that already has one."""
        if conn.role in CAPTURE_ROLES:
            if self.capture is not None:
                return False
            self.capture = conn
            if self.orchestrator is None:
                from pulselens.orchestrator import run_session

                self.orchestrator = asyncio.get_running_loop().create_task(run_session(self))
        if conn.role in ("lab", "presenter"):
            start = from_seq if from_seq is not None else (0 if conn.role == "presenter" else len(self.bus.events))
            for event in self.bus.since(start):  # catch-up and subscribe with no await between: no gap, no repeat
                conn.send(EventMessage(event=event).model_dump())
            conn.unsubscribe = self.bus.subscribe(lambda e: conn.send(EventMessage(event=e).model_dump()))
        return True

    def detach(self, conn: Connection) -> None:
        conn.close()
        if self.capture is conn:
            self.capture = None

    def send_capture(self, msg: BaseModel) -> None:
        """To the capture device, if one is connected. Customer messages are checked in Connection.send."""
        if self.capture is not None:
            self.capture.send(msg.model_dump())

    # --- messages from the capture device ---

    def on_message(self, conn: Connection, raw: dict[str, Any]) -> None:
        if conn is not self.capture:
            return  # viewers only listen
        kind = raw.get("type")
        if kind == "ack":
            self.on_ack(raw)
        elif kind == "stage.done":
            self.on_stage_done(raw)
        elif kind != "heartbeat":
            self.bus.emit("error", {"code": "unknown_message", "message": f"capture sent {kind!r}"})

    def on_stage_done(self, raw: dict[str, Any]) -> None:
        try:
            msg = StageDone.model_validate(raw)
        except ValidationError:
            self.bus.emit("error", {"code": "bad_message", "message": "invalid stage.done"})
            return
        if msg.stage == "coach":
            for r in msg.data.get("rounds") or []:
                for tip in r.get("tips") or []:
                    self.bus.emit("coach.tip", {"tip": tip, "round": r.get("round")})
        fut = self.stage_done.get(msg.stage)
        if fut is not None and not fut.done():
            fut.set_result(msg.data)

    def on_ack(self, raw: dict[str, Any]) -> None:
        """Accept each pulse's ack once (signature must match); a late one is logged ok:false (SPEC 6)."""
        try:
            ack = PulseAck.model_validate(raw)
        except ValidationError:
            self.bus.emit("error", {"code": "bad_ack", "message": "ack does not match PulseAck"})
            return
        state = self.pulses.get(ack.pulse_id)
        if state is None:
            self.bus.emit("error", {"code": "unknown_pulse", "message": f"ack for unknown pulse {ack.pulse_id}"})
            return
        if not same_signature(ack.sig, state.sig):
            self.bus.emit(
                "error", {"code": "bad_signature", "message": f"ack for {ack.pulse_id} has the wrong signature"}
            )
            return
        if state.acked:
            self.bus.emit("error", {"code": "duplicate_ack", "message": f"pulse {ack.pulse_id} was already acked"})
            return
        state.acked = True
        expires = self.hub.orchestrator.expires_in_ms
        late_server = self.hub.clock() > state.deadline
        late_client = ack.painted is not None and ack.painted - ack.received > expires
        late = late_server or late_client
        ok = ack.ok and not late
        self.record_pulse(state, ack, ok=ok, error="late" if late else ack.error)
        self.bus.emit("pulse.acked", {"pulse_id": ack.pulse_id, "painted": ack.painted, "ended": ack.ended, "ok": ok})
        if not state.done.done():
            state.done.set_result(ok)

    def record_pulse(self, state: PulseState, ack: PulseAck | None, *, ok: bool, error: str | None) -> None:
        """One pulses.jsonl line (SPEC 4.1), with the server's release and ack times."""
        self.hub.store.append_jsonl(
            self.session_id,
            "pulses.jsonl",
            [
                {
                    "pulse_id": state.pulse_id,
                    "kind": state.kind,
                    "source": state.source,
                    "params": state.params,
                    "received": ack.received if ack else None,
                    "applied": ack.applied if ack else None,
                    "painted": ack.painted if ack else None,
                    "ended": ack.ended if ack else None,
                    "ok": ok,
                    "sig": state.sig,
                    "shown": ack.shown if ack else None,
                    "error": error,
                    "t_released": state.released,
                    "t_acked": self.hub.clock() if ack else None,
                }
            ],
        )


class Hub:
    """All live sessions of this server process."""

    def __init__(
        self, store: SessionStore, settings: Settings, orchestrator: Any, clock: Callable[[], float], pair_ttl_ms: float
    ) -> None:
        self.store = store
        self.settings = settings
        self.orchestrator = orchestrator  # OrchestratorConfig
        self.clock = clock
        self.pairing = PairingRegistry(pair_ttl_ms, clock)
        self._runtimes: dict[str, SessionRuntime] = {}

    def create(self, body: SessionCreate) -> SessionCreated:
        sid = self.store.create(body.mode, body.product, body.scenario, body.label.model_dump() if body.label else None)
        rt = self.runtime(sid)
        assert rt is not None
        rt.bus.emit("session.created", {"mode": body.mode, "scenario": body.scenario, "product": body.product})
        return SessionCreated(
            session_id=sid,
            pair_code=self.pairing.issue(sid),
            ws_url=f"/ws/session/{sid}",
            token=self.console_token(sid),
        )

    def console_token(self, session_id: str) -> str:
        """HMAC of the session id: the creator's key to scores and events. Needs no storage, survives a restart,
        and cannot be derived from the session id the customer learns by pairing."""
        mac = hmac.new(self.settings.pulse_hmac_secret.encode(), f"console|{session_id}".encode(), hashlib.sha256)
        return mac.hexdigest()[:32]

    def token_ok(self, session_id: str, token: str | None) -> bool:
        return bool(token) and hmac.compare_digest(token.encode(), self.console_token(session_id).encode())

    def runtime(self, session_id: str) -> SessionRuntime | None:
        """The live runtime, loaded from disk for sessions created before a restart; None when unknown."""
        rt = self._runtimes.get(session_id)
        if rt is None and self.store.exists(session_id):
            rt = self._runtimes[session_id] = SessionRuntime(self, session_id)
        return rt

    async def shutdown(self) -> None:
        for rt in self._runtimes.values():
            if rt.orchestrator and not rt.orchestrator.done():
                rt.orchestrator.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await rt.orchestrator
