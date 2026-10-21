"""JSON shapes shared by the server and both sites (SPEC 4.2 and 5). Source of truth.

packages/types/src/models.gen.ts is generated from this file by `make types`
(scripts/gen_types.py); test_types_mirror.py fails when the two drift.
Field descriptions become JSDoc in the TypeScript mirror.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["mobile_browser", "desktop_browser"]
ClockSource = Literal["captureTime", "rvfc", "videoframe", "raf"]
GyroState = Literal["available", "granted", "denied", "absent"]
Family = Literal["camera", "optical", "motion", "content", "physiology", "continuity"]
CheckStatus = Literal["pending", "running", "pass", "fail", "abstain"]
ThresholdSource = Literal["profile", "channel", "pooled", "bootstrap", "rule"]
Route = Literal["PASS", "ADD_CHECKS", "AGENT_CHALLENGE", "ASSISTED_KYC", "HOLD"]
Stage = Literal["camera", "coach", "plan", "pulses", "face", "decide"]
SessionMode = Literal["live", "step", "superset"]
PulseKind = Literal["light", "tilt", "hand", "lens", "photo"]
PulseSource = Literal["orchestrator", "agent"]
LightMode = Literal["colour", "split", "white"]
AgentActionName = Literal["fire_light", "fire_tilt", "take_photo", "approve", "escalate", "assisted"]
AttackTool = Literal["screen_replay", "premade_injection", "liveportrait", "liveswap", "source_switch", "emulator"]
EventType = Literal[
    "session.created",
    "stage.changed",
    "camera.details",
    "probe.step",
    "camera.summary",
    "coach.tip",
    "plan.decided",
    "pulse.released",
    "pulse.acked",
    "signal.chunk",
    "check.started",
    "check.result",
    "coverage.update",
    "continuity.update",
    "photo.taken",
    "decision",
    "agent.action",
    "orchestrator.waiting",
    "error",
]

# Literal aliases exported by name to TypeScript (gen_types.py).
LITERAL_ALIASES = {
    "Channel": Channel,
    "ClockSource": ClockSource,
    "GyroState": GyroState,
    "Family": Family,
    "CheckStatus": CheckStatus,
    "ThresholdSource": ThresholdSource,
    "Route": Route,
    "Stage": Stage,
    "SessionMode": SessionMode,
    "PulseKind": PulseKind,
    "PulseSource": PulseSource,
    "LightMode": LightMode,
    "AttackTool": AttackTool,
    "AgentActionName": AgentActionName,
    "EventType": EventType,
}


class Model(BaseModel):
    # The server always serialises every field (None as null), so the TS mirror marks every field required.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class CameraDetails(Model):
    channel: Channel
    browser: str
    os: str
    ua_mobile: bool | None
    camera_label: str
    device_id_hash: str
    settings: dict[str, Any] = Field(description="width, height, frameRate, facingMode, aspectRatio, resizeMode")
    capabilities: dict[str, Any] = Field(description="ranges + exposure/whiteBalance/zoom/torch/focus presence")
    native_modes: list[dict[str, Any]] = Field(description="filled by the mode-switch probe")
    fps_median: float | None
    fps_jitter_ms: float | None
    clock_source: ClockSource
    rvfc: bool
    resize_mode_supported: bool
    gyro: GyroState
    screen: dict[str, Any] = Field(description="w, h, dpr, refresh_hz_estimate")
    webgl_renderer: str | None
    webdriver: bool
    profile_claimed: str | None
    profile_measured: str | None
    noise_curve: dict[str, Any] | None = Field(description="slope, intercept, r2, per-channel")
    fingerprint_pce: float | None


class CheckResult(Model):
    check_id: str
    unit: str
    family: Family
    status: CheckStatus
    score: float | None = Field(description="higher is more suspicious")
    threshold: float | None
    threshold_source: ThresholdSource | None
    band: dict[str, Any] | None = Field(
        description='genuine band for display, e.g. {"lo": -10, "hi": 25, "unit": "ms", "n": 18}'
    )
    quality: float = Field(description="0..1; the check abstains below quality.min")
    features: dict[str, float]
    reason: str = Field(description="one plain sentence with real counts")
    explainer: str = Field(description='key into EXPLAINERS.md, e.g. "check.optical.face_neck"')
    plot: dict[str, Any] | None = Field(
        description='{"type": "echo" | "split" | "tilt" | "noise" | "modes" | "continuity", "ref": "..."}'
    )
    evidence_frames: list[int] = []


class PlanDecision(Model):
    units: list[dict[str, Any]] = Field(description="{unit, reason, effort, duration_s}")
    skipped: list[dict[str, Any]] = Field(description="{unit, reason}")
    coverage_expected: dict[str, list[str]]
    route_hint: str | None
    effort_used: float
    effort_cap: float


class SessionDecision(Model):
    route: Route
    coverage: dict[str, list[str]]
    failed_families: list[str]
    continuity_ok: bool
    photo_bound: bool
    reasons: list[str]
    needs_human: bool
    provisional_thresholds: bool


class Event(Model):
    """One entry of the per-session event stream (SPEC 5), in events.jsonl and on /ws/session/{id}."""

    seq: int = Field(description="strictly increasing per session, from 0")
    t_server: float = Field(description="server clock when the event was emitted, ms")
    t_client: float | None = Field(default=None, description="client performance.now() ms, when the event came from it")
    type: EventType
    payload: dict[str, Any]


# --- REST shapes (SPEC 6) ---------------------------------------------------------------------------------------


class RecordingLabel(Model):
    """Lab Record operator form (SPEC 13.3), stored in meta.json."""

    person: str = Field(description='pseudonymous person code, e.g. "P01"')
    device: str = Field(description='device code, e.g. "D03"')
    light: Literal["normal", "dim"]
    kind: Literal["genuine", "attack"]
    tool: AttackTool | None = Field(description="set when kind is attack")
    consent_ref: str


class SessionCreate(Model):
    """Body of POST /api/sessions."""

    mode: SessionMode
    product: str = Field(description='"lab" or "demo"')
    scenario: str | None = None
    label: RecordingLabel | None = None


class SessionCreated(Model):
    """Response of POST /api/sessions."""

    session_id: str
    pair_code: str
    ws_url: str = Field(description="path of the session WebSocket, e.g. /ws/session/<id>")


class FrameMeta(Model):
    """One frames.jsonl line; the client sends these as the `meta` part of each frames batch."""

    i: int = Field(description="frame index from 0, in capture order")
    t: float = Field(description="canonical frame time, performance.now() domain, ms")
    capture_time: float | None
    presented_frames: int | None
    w: int
    h: int
    file: str = Field(description="working frame file name, e.g. 000123.jpg")
    fp_file: str | None = Field(default=None, description="fingerprint frame file name, every fp_every-th frame")


# --- WebSocket capture messages (SPEC 6), sent to the capture device (customer or lab role) -------------------


class LightParams(Model):
    """params of a light pulse. Hues index the isoluminant set; the client reports the colours it painted."""

    mode: LightMode
    hue_deg: float | None = Field(default=None, description="colour mode")
    left_hue_deg: float | None = Field(default=None, description="split mode, left half")
    right_hue_deg: float | None = Field(default=None, description="split mode, right half")
    duration_ms: int


class StageMessage(Model):
    type: Literal["stage"] = "stage"
    stage: Stage
    prompt: str | None = Field(default=None, description="explainer key of the customer prompt, e.g. prompt.light")


class PromptMessage(Model):
    type: Literal["prompt"] = "prompt"
    key: str = Field(description="explainer key, e.g. prompt.coach.closer")


class PulseMessage(Model):
    type: Literal["pulse"] = "pulse"
    pulse_id: str
    kind: PulseKind
    source: PulseSource
    params: dict[str, Any] = Field(description="LightParams for kind light")
    sig: str = Field(description="HMAC_SHA256(secret, pulse_id|kind|params|session_id), hex")


class DoneMessage(Model):
    type: Literal["done"] = "done"
    key: str = Field(description="prompt.done, prompt.retry, prompt.agent or prompt.branch")


# --- WebSocket messages from the capture device --------------------------------------------------------------


class PulseAck(Model):
    """Client timing of one pulse, performance.now() ms (SPEC 7.4). Becomes a pulses.jsonl line on the server."""

    type: Literal["ack"] = "ack"
    pulse_id: str
    sig: str
    received: float
    applied: float | None
    painted: float | None
    ended: float | None
    ok: bool
    error: str | None = Field(default=None, description="why ok is false, e.g. rate_limit, bad_params")
    shown: dict[str, Any] | None = Field(
        default=None, description="light: sRGB 0-255 actually painted, {neutral, rgb} or {neutral, left, right}"
    )


class StageDone(Model):
    """The client finished a stage it runs itself (camera details, coaching)."""

    type: Literal["stage.done"] = "stage.done"
    stage: Stage
    data: dict[str, Any]


class Heartbeat(Model):
    type: Literal["heartbeat"] = "heartbeat"
    t: float


# --- Viewers (presenter and lab roles) and the remaining REST shapes ------------------------------------------------


class EventMessage(Model):
    """Every event, pushed to presenter and lab connections (never to the customer role)."""

    type: Literal["event"] = "event"
    event: Event


class PairJoined(Model):
    """Response of POST /api/pair/{code}."""

    session_id: str
    role: Literal["customer"] = "customer"



class AgentRequest(Model):
    """Body of POST /api/sessions/{id}/agent (needs X-Console-Passcode)."""

    action: AgentActionName
    note: str = ""


# Models mirrored to TypeScript, in output order.
EXPORTED_MODELS: tuple[type[BaseModel], ...] = (
    CameraDetails, CheckResult, PlanDecision, SessionDecision, Event,
    RecordingLabel, SessionCreate, SessionCreated, FrameMeta,
    LightParams, StageMessage, PromptMessage, PulseMessage, DoneMessage,
    PulseAck, StageDone, Heartbeat, EventMessage, PairJoined, AgentRequest,
)
