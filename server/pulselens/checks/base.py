"""What every check receives and returns (SPEC 9). Checks are pure: region means + pulse log in, CheckResult out.

CLAUDE.md rule 2: checks never throw on bad input. `guarded` turns any exception into an abstain with a reason.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from pulselens.calibration.thresholds import Thresholds
from pulselens.models import CheckResult, CheckStatus, ThresholdSource
from pulselens.planner.registry import CheckSpec
from pulselens.vision.linearize import srgb_to_linear
from pulselens.vision.noise import NoiseCurve
from pulselens.vision.prnu import Fingerprint


@dataclass(frozen=True)
class RegionSeries:
    """Per-frame mean linear RGB of one region (N, 3) and how much of it was in view (N,), 0 = absent."""

    rgb: np.ndarray
    coverage: np.ndarray


def _linear(rgb: Any) -> np.ndarray | None:
    if not isinstance(rgb, list | tuple) or len(rgb) != 3:
        return None
    return srgb_to_linear(np.asarray(rgb, dtype=np.float64) / 255.0)


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, int | float) and math.isfinite(x) else None


@dataclass(frozen=True)
class Pulse:
    """One pulses.jsonl line, with the colours actually painted (ack `shown`) in linear RGB."""

    pulse_id: str
    kind: str
    mode: str | None
    painted: float | None
    ended: float | None
    ok: bool
    colour: np.ndarray | None = None  # colour and white pulses
    left: np.ndarray | None = None  # split pulses
    right: np.ndarray | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_log(cls, d: Mapping[str, Any]) -> Pulse:
        params = d.get("params") or {}
        shown = d.get("shown") or {}
        return cls(
            pulse_id=str(d.get("pulse_id", "")),
            kind=str(d.get("kind", "")),
            mode=params.get("mode"),
            painted=_num(d.get("painted")),
            ended=_num(d.get("ended")),
            ok=bool(d.get("ok")),
            colour=_linear(shown.get("rgb")),
            left=_linear(shown.get("left")),
            right=_linear(shown.get("right")),
            params=params,
        )

    @property
    def is_colour(self) -> bool:
        """A usable colour pulse for the echo checks (SPEC 9.3: light.delay and face_neck use colour pulses)."""
        return (
            self.kind == "light"
            and self.mode == "colour"
            and self.ok
            and self.painted is not None
            and self.colour is not None
        )


@dataclass(frozen=True)
class AnalysisContext:
    t: np.ndarray  # frame times, performance.now() ms
    regions: Mapping[str, RegionSeries]
    pulses: tuple[Pulse, ...]
    thresholds: Thresholds
    profile: str | None = None
    quality_min: float = 0.5  # config quality.min
    min_fps: float = 12.0  # config quality.min_fps: below it every check abstains (SPEC 7.6)
    # Camera reality evidence (SPEC 9.2), measured while the frames are read; empty when not measured.
    details: Mapping[str, Any] = field(default_factory=dict)  # meta.json camera_details
    probe: tuple[Mapping[str, Any], ...] = ()  # probe.jsonl rows
    presented: np.ndarray = field(default_factory=lambda: np.empty(0))  # presented_frames per frame (nan if unknown)
    noise: NoiseCurve | None = None
    fingerprint: Fingerprint | None = None
    duplicates: tuple[int, int] | None = None  # (exact repeats of the previous frame, frames compared)

    @property
    def colour_pulses(self) -> list[Pulse]:
        return [p for p in self.pulses if p.is_colour]

    @property
    def fps(self) -> float | None:
        """Median frame rate from the frame times, or None with fewer than 3 frames."""
        d = np.diff(np.asarray(self.t, dtype=np.float64))
        d = d[np.isfinite(d) & (d > 0)]
        return 1000.0 / float(np.median(d)) if len(d) >= 2 else None


def clean_features(features: Mapping[str, float | int | None]) -> dict[str, float]:
    """CheckResult.features holds finite floats only."""
    return {k: float(v) for k, v in features.items() if v is not None and math.isfinite(float(v))}


def result(
    spec: CheckSpec,
    status: CheckStatus,
    reason: str,
    *,
    score: float | None = None,
    threshold: float | None = None,
    source: ThresholdSource | None = None,
    quality: float = 0.0,
    features: Mapping[str, float | int | None] | None = None,
    band: dict | None = None,
    evidence_frames: list[int] | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=spec.check_id,
        unit=spec.unit,
        family=spec.family,
        status=status,
        score=score if score is None or math.isfinite(score) else None,
        threshold=threshold,
        threshold_source=source,
        band=band,
        quality=float(min(1.0, max(0.0, quality))),
        features=clean_features(features or {}),
        reason=reason,
        explainer=spec.explainer,
        plot={"type": spec.plot, "ref": spec.check_id},
        evidence_frames=evidence_frames or [],
    )


def abstain(
    spec: CheckSpec, reason: str, *, quality: float = 0.0, features: Mapping[str, float | int | None] | None = None
):
    return result(spec, "abstain", reason, quality=quality, features=features)


def too_slow(spec: CheckSpec, ctx: AnalysisContext) -> list[CheckResult] | None:
    """The SPEC 7.6 floor: below `min_fps` frames are too far apart to time anything, so the check abstains."""
    fps = ctx.fps
    if fps is not None and fps < ctx.min_fps:
        return [
            abstain(
                spec,
                f"The camera delivered {fps:.1f} fps, below the {ctx.min_fps:.0f} fps needed to time the echo.",
                features={"fps": fps},
            )
        ]
    return None


Run = Callable[[AnalysisContext], list[CheckResult]]


def guarded(spec: CheckSpec) -> Callable[[Run], Run]:
    """Any exception inside a check becomes an abstain, never a crash or a fail (CLAUDE.md rule 2)."""

    def wrap(run: Run) -> Run:
        @functools.wraps(run)
        def safe(ctx: AnalysisContext) -> list[CheckResult]:
            try:
                return run(ctx)
            except Exception as e:  # noqa: BLE001 -- by design
                return [abstain(spec, f"Could not be measured ({type(e).__name__}: {e}).")]

        return safe

    return wrap
