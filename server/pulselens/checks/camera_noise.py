"""camera.noise_curve (SPEC 9.2): temporal noise on still pixels against brightness, var = a * mu + b per channel
(vision/noise.py). Video that was rendered, denoised or re-encoded is too clean for a sensor. After the camera's own
processing the curve does not always rise, so only "too clean" is judged until genuine profiles are calibrated."""

from __future__ import annotations

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("camera.noise_curve", "camera", "camera", "check.camera.noise_curve", "noise")


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    curve = ctx.noise
    if curve is None:
        return [abstain(SPEC, "Not enough still picture at enough brightness levels to measure the noise curve.")]
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    mid, limit = curve.noise_mid, float(params["min_noise_mid"])
    features = {"noise_mid": mid, "pairs": curve.pairs, "static_share": curve.static_share}
    for name, c in curve.channels.items():
        features |= {f"slope_{name}": c.slope, f"intercept_{name}": c.intercept, f"r2_{name}": c.r2}
    green = curve.channels["g"]
    if mid < limit:
        status, reason = "fail", f"Noise at mid-grey is {mid:.4f}, cleaner than any sensor (limit {limit:.4f})."
    else:
        status = "pass"
        reason = (
            f"Noise at mid-grey is {mid:.4f} (limit {limit:.4f}); it changes with brightness at slope "
            f"{green.slope:.1e} (green, fit R² {green.r2:.2f})."
        )
    return [
        result(
            SPEC,
            status,
            reason,
            score=-mid,
            threshold=-limit,
            source=source,
            quality=min(1.0, curve.pairs / 20),
            features=features,
        )
    ]
