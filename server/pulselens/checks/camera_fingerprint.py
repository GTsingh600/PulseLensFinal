"""camera.fingerprint (SPEC 9.2): the sensor's fixed pixel pattern (PRNU) estimated on odd and even fingerprint
frames separately, compared by PCE (vision/prnu.py). Generated video, or video passed through software that
resamples it, has none."""

from __future__ import annotations

import math

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register
from pulselens.vision.prnu import LUMA_RANGE, MIN_FRAMES

SPEC = CheckSpec("camera.fingerprint", "camera", "camera", "check.camera.fingerprint", "noise")


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    fp = ctx.fingerprint
    if fp is None:
        return [
            abstain(
                SPEC,
                f"Fewer than {MIN_FRAMES} fingerprint frames with mean brightness between {LUMA_RANGE[0]} and "
                f"{LUMA_RANGE[1]} (too dark, too bright or too short).",
            )
        ]
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    limit = float(params["min_pce"])
    ok = fp.pce >= limit
    reason = (
        f"The sensor pattern in odd frames matches the even frames (PCE {fp.pce:.0f}, limit {limit:.0f})."
        if ok
        else f"No stable sensor pattern: PCE {fp.pce:.1f} (limit {limit:.0f}) over {fp.frames} frames."
    )
    return [
        result(
            SPEC,
            "pass" if ok else "fail",
            reason,
            score=-math.log10(max(fp.pce, 1e-3)),
            threshold=-math.log10(limit),
            source=source,
            quality=min(1.0, fp.frames / (2 * MIN_FRAMES)),
            features={"pce": fp.pce, "frames": fp.frames, "skipped": fp.skipped},
        )
    ]
