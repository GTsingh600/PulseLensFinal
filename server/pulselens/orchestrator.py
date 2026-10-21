"""Orchestrator stub (M1.2): camera stage, coaching, then the light suite with just-in-time signed pulses.

The planner, the other pulse kinds and live analysis come with M3.3. Step mode waits for /next before each stage.
Every wait has a timeout, so a capture device that disappears never hangs the session.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any

from pulselens.config import load_config
from pulselens.hub import PulseState, SessionRuntime
from pulselens.models import DoneMessage, PulseMessage, StageMessage
from pulselens.pulses import light_suite, sign_pulse

CLIENT_STAGES = ("camera", "coach")  # stages the capture device runs and reports with stage.done


@dataclass(frozen=True)
class OrchestratorConfig:
    stage_timeout_s: float = 45.0  # camera details and up to two coaching rounds
    gap_ms: tuple[float, float] = (700, 1300)
    release_jitter_ms: tuple[float, float] = (0, 400)
    duration_ms: int = 400
    expires_in_ms: float = 300  # a pulse painted later than this after it arrived is late
    ack_grace_ms: float = 1500  # network and rendering slack on top of duration + expiry before an ack is late
    colour: int = 6
    split: int = 2
    white: int = 2

    @classmethod
    def from_config(cls) -> OrchestratorConfig:
        p = load_config()["pulses"]
        light = p["light"]
        return cls(
            gap_ms=tuple(light["gap_ms"]),
            release_jitter_ms=tuple(p["release_jitter_ms"]),
            duration_ms=int(light["duration_ms"]),
            expires_in_ms=float(light["expires_in_ms"]),
            colour=int(light["colour"]),
            split=int(light["split"]),
            white=int(light["white"]),
        )


async def _gate(rt: SessionRuntime, stage: str) -> None:
    if rt.mode != "step":
        return
    rt.next_stage.clear()
    rt.waiting_for = stage
    rt.bus.emit("orchestrator.waiting", {"next": stage})
    try:
        await rt.next_stage.wait()
    finally:
        rt.waiting_for = None


async def _client_stage(rt: SessionRuntime, stage: str, cfg: OrchestratorConfig) -> None:
    fut = rt.stage_done[stage] = asyncio.get_running_loop().create_future()
    rt.send_capture(StageMessage(stage=stage))
    try:
        await asyncio.wait_for(fut, cfg.stage_timeout_s)
    except TimeoutError:
        rt.bus.emit(
            "error", {"code": "stage_timeout", "message": f"no stage.done for {stage} in {cfg.stage_timeout_s:.0f} s"}
        )


def _release(rt: SessionRuntime, k: int, params: dict[str, Any], cfg: OrchestratorConfig) -> PulseState:
    """Signs and sends one pulse at the moment it is due (just in time)."""
    pulse_id = f"{rt.session_id}-{k}"
    sig = sign_pulse(rt.hub.settings.pulse_hmac_secret, pulse_id, "light", params, rt.session_id)
    now = rt.hub.clock()
    state = PulseState(
        pulse_id=pulse_id,
        kind="light",
        source="orchestrator",
        params=params,
        sig=sig,
        released=now,
        deadline=now + params["duration_ms"] + cfg.expires_in_ms + cfg.ack_grace_ms,
    )
    rt.pulses[pulse_id] = state
    rt.bus.emit("pulse.released", {"pulse_id": pulse_id, "kind": "light", "params": params, "source": "orchestrator"})
    rt.send_capture(PulseMessage(pulse_id=pulse_id, kind="light", source="orchestrator", params=params, sig=sig))
    return state


async def run_session(rt: SessionRuntime) -> None:
    cfg = rt.hub.orchestrator
    try:
        for stage in CLIENT_STAGES:
            await _gate(rt, stage)
            rt.bus.emit("stage.changed", {"stage": stage, "status": "started"})
            await _client_stage(rt, stage, cfg)

        await _gate(rt, "pulses")
        rt.bus.emit("stage.changed", {"stage": "pulses", "status": "started"})
        rt.send_capture(StageMessage(stage="pulses", prompt="prompt.light"))
        plan = light_suite(cfg.colour, cfg.split, cfg.white, cfg.duration_ms, rt.rng)
        for k, params in enumerate(plan):
            await asyncio.sleep((rt.rng.uniform(*cfg.gap_ms) + rt.rng.uniform(*cfg.release_jitter_ms)) / 1000)
            state = _release(rt, k, params, cfg)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(state.done), (state.deadline - state.released) / 1000)
        rt.send_capture(DoneMessage(key="prompt.done"))
    finally:
        for state in rt.pulses.values():
            if not state.acked:
                state.acked = True  # an ack arriving after the session is over is a duplicate, not a record
                rt.record_pulse(state, None, ok=False, error="no_ack")
