"""camera.timing (SPEC 9.2): the gaps between frames.

Features: median fps, coefficient of variation of the intervals, share within ±0.5 ms of the median, longest gap.
Until calibration gives genuine bands per profile only a stall is judged (a gap over `max_gap_ms`); evenness is
measured and shown, not voted on: hardware-timestamped webcams are very even too.
"""

from __future__ import annotations

import numpy as np

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("camera.timing", "camera", "camera", "check.camera.timing", "modes")
MIN_FRAMES = 30


def timing_features(t: np.ndarray) -> dict[str, float] | None:
    d = np.diff(np.asarray(t, dtype=np.float64))
    d = d[np.isfinite(d) & (d > 0)]
    if len(d) < MIN_FRAMES:
        return None
    median = float(np.median(d))
    return {
        "fps": 1000.0 / median,
        "cv": float(np.std(d) / np.mean(d)),
        "exact_share": float(np.mean(np.abs(d - median) <= 0.5)),
        "longest_gap_ms": float(d.max()),
    }


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    features = timing_features(ctx.t)
    if features is None:
        return [abstain(SPEC, f"Too few frames to judge the timing (need {MIN_FRAMES + 1}).")]
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    limit = float(params["max_gap_ms"])
    gap = features["longest_gap_ms"]
    if gap > limit:
        status = "fail"
        reason = f"The video stopped for {gap:.0f} ms (limit {limit:.0f} ms), as a stalled software source does."
    else:
        status = "pass"
        reason = (
            f"{features['fps']:.1f} fps, interval spread {features['cv']:.0%}, longest gap {gap:.0f} ms; "
            "evenness is compared with genuine devices once calibrated."
        )
    return [result(SPEC, status, reason, score=gap, threshold=limit, source=source, quality=1.0, features=features)]
