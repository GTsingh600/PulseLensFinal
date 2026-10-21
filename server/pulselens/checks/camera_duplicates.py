"""camera.duplicates (SPEC 9.2): frames that are exact copies of the one before (dHash distance 0 and mean
absolute difference < 0.5). Relays and virtual cameras repeat frames when they cannot keep up."""

from __future__ import annotations

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("camera.duplicates", "camera", "camera", "check.camera.duplicates", "modes")


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    if ctx.duplicates is None or ctx.duplicates[1] < int(params["min_frames"]):
        return [abstain(SPEC, "Too few frames were read to count repeats.")]
    repeats, compared = ctx.duplicates
    share = repeats / compared
    limit = float(params["max_share"])
    return [
        result(
            SPEC,
            "fail" if share > limit else "pass",
            f"{repeats} of {compared} frames repeated the one before ({share:.1%}; limit {limit:.0%}).",
            score=share,
            threshold=limit,
            source=source,
            quality=1.0,
            features={"repeats": repeats, "compared": compared, "share": share},
        )
    ]
