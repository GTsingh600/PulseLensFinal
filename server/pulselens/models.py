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


# Models mirrored to TypeScript, in output order.
EXPORTED_MODELS: tuple[type[BaseModel], ...] = (CameraDetails, CheckResult, PlanDecision, SessionDecision, Event)
