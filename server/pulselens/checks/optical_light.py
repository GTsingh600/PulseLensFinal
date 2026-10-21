"""optical.light.delay (SPEC 9.3): median delay from each colour flash to the face's colour change.

A pulse with no echo counts as 1000 ms (a replay never answers). Needs at least 4 valid pulses.
Score = |median - center| in ms, against the profile's centre (bootstrap until calibrated).
"""

from __future__ import annotations

import numpy as np

from pulselens.checks.base import AnalysisContext, abstain, guarded, result, too_slow
from pulselens.checks.echo import NO_ECHO_MS, echo_onset
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("optical.light.delay", "optical", "light", "check.optical.light.delay", "echo")
MIN_VALID = 4


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    pulses = ctx.colour_pulses
    skin = ctx.regions.get("skin")
    if skin is None or not len(ctx.t):
        return [abstain(SPEC, "No face measurements in this session.")]
    if not pulses:
        return [abstain(SPEC, "No colour pulses were painted in this session.")]
    if slow := too_slow(SPEC, ctx):
        return slow
    a_min = float(ctx.thresholds.echo["a_min"])
    onsets = [echo_onset(ctx.t, skin, p, region="skin", a_min=a_min) for p in pulses]
    valid = [o for o in onsets if o.valid]
    quality = len(valid) / len(pulses)
    if len(valid) < MIN_VALID or quality < ctx.quality_min:
        return [
            abstain(
                SPEC,
                f"Only {len(valid)} of {len(pulses)} colour pulses could be measured on the face (need {MIN_VALID}).",
                quality=quality,
                features={"n_valid": len(valid), "n_pulses": len(pulses)},
            )
        ]

    delays = np.array([o.onset_ms if o.onset_ms is not None else NO_ECHO_MS for o in valid])
    n_echo = sum(o.onset_ms is not None for o in valid)
    median = float(np.median(delays))
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    center, tol = float(params["center_ms"]), float(params["tolerance_ms"])
    score = abs(median - center)
    status = "pass" if score <= tol else "fail"
    label = "provisional band" if source == "bootstrap" else "band for this device type"
    if n_echo == 0:
        reason = f"The face did not change colour after any flash (0 of {len(valid)} pulses), as a replay would."
    else:
        reason = (
            f"The face echoed on {n_echo} of {len(valid)} colour pulses; median delay {median:.0f} ms "
            f"({label} {center - tol:.0f} to {center + tol:.0f} ms)."
        )
    echoed = delays[delays < NO_ECHO_MS]
    return [
        result(
            SPEC,
            status,
            reason,
            score=score,
            threshold=tol,
            source=source,
            quality=quality,
            features={
                "median_ms": median,
                "n_valid": len(valid),
                "n_echo": n_echo,
                "n_pulses": len(pulses),
                "iqr_ms": float(np.subtract(*np.percentile(echoed, [75, 25]))) if len(echoed) >= 2 else None,
                "median_amplitude": float(np.median([o.amplitude for o in valid if o.amplitude is not None]))
                if n_echo
                else None,
            },
        )
    ]
