"""optical.face_neck (SPEC 9.3): does the face change colour with the neck (or shirt) after each flash?

The flash reaches both in the same frame, so the device's own delay cancels out. A face-swap redraws only the
face, so its echo comes later or weaker than the neck's. Per colour pulse: Δ = t_face - t_neck, each timed at half
of its own echo height (constant fraction, so a weak face and a strong shirt are not a frame apart), and the
amplitude ratio A_face / A_neck.
- A clear neck echo with a silent face on most measured pulses is a strong fail (rule). Silent means the face never
  crossed its threshold although that threshold was low enough to hear even the weakest real echo (a quarter of the
  neck's); a face too noisy to tell counts for neither side, and a weak face echo counts as the face answering.
- Abstains when the neck is out of frame, saturated, or its echo is too weak to compare.
- Score = |median Δ - center| / scale + ratio deviation beyond its tolerance; fails above tau.
"""

from __future__ import annotations

import math

import numpy as np

from pulselens.checks.base import AnalysisContext, abstain, guarded, result, too_slow
from pulselens.checks.echo import MIN_COVERAGE, echo_onset
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("optical.face_neck", "optical", "light", "check.optical.face_neck", "echo")
STRONG_FAIL_MIN = 2  # neck-only pulses needed for the rule


def _clear(o, params) -> bool:
    """An echo strong enough to time: its hold amplitude reaches `min_snr` times its own detection threshold."""
    return bool(o.amplitude and o.threshold and o.amplitude >= float(params.get("min_snr", 2.0)) * o.threshold)


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    skin, neck = ctx.regions.get("skin"), ctx.regions.get("neck")
    pulses = ctx.colour_pulses
    if skin is None or neck is None or not len(ctx.t):
        return [abstain(SPEC, "No face or neck measurements in this session.")]
    if not pulses:
        return [abstain(SPEC, "No colour pulses were painted in this session.")]
    if slow := too_slow(SPEC, ctx):
        return slow
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)

    face_seen = skin.coverage >= MIN_COVERAGE
    if not face_seen.any():
        return [abstain(SPEC, "No face was found in the frames.")]
    neck_cov = float(np.median(neck.coverage[face_seen]))
    if neck_cov < params["neck_min_coverage"]:
        return [
            abstain(
                SPEC,
                f"The neck was out of frame ({neck_cov:.0%} of the neck area visible); ask to show the shoulders.",
                features={"neck_coverage": neck_cov},
            )
        ]
    neck_level = np.nanmedian(neck.rgb[face_seen].max(axis=1))
    if not math.isfinite(neck_level):
        return [abstain(SPEC, "The neck region could not be measured.")]
    if neck_level > params["saturation"]:
        return [
            abstain(
                SPEC,
                "The neck region was saturated (too bright to see a colour change).",
                features={"neck_level": neck_level},
            )
        ]

    a_min = float(ctx.thresholds.echo["a_min"])
    lags, ratios, neck_only, face_only, measured, weak, unclear = [], [], 0, 0, 0, 0, 0
    ratio_floor = math.exp(-float(params["ratio_log_tolerance"]))  # the weakest face/neck ratio a real face shows
    for p in pulses:
        f = echo_onset(ctx.t, skin, p, region="skin", a_min=a_min)
        n = echo_onset(ctx.t, neck, p, region="neck", a_min=a_min)
        if not (f.valid and n.valid):
            continue
        if n.onset_cf_ms is not None and f.onset_cf_ms is not None:
            measured += 1  # the face answered this flash, even if too weakly to time
            if not (_clear(f, params) and _clear(n, params)):
                weak += 1  # both echoed, but too close to the noise to time against each other
                continue
            lags.append(f.onset_cf_ms - n.onset_cf_ms)
            if f.amplitude and n.amplitude and f.amplitude > 0 and n.amplitude > 0:
                ratios.append(f.amplitude / n.amplitude)
        elif n.onset_ms is not None and _clear(n, params):
            # "Silent" only if the face was quiet enough that even the weakest real echo (the neck's amplitude
            # times ratio_floor) would have crossed its threshold; otherwise the face was just too noisy to tell.
            audible = (f.threshold or 0.0) <= ratio_floor * (n.amplitude or 0.0)
            if audible and (f.peak is None or f.peak < (f.threshold or 0.0)):
                measured += 1
                neck_only += 1
            else:
                unclear += 1
        elif f.onset_ms is not None and n.onset_ms is None:
            face_only += 1

    base = {
        "n_pulses": len(pulses),
        "n_pairs": len(lags),
        "n_neck_only": neck_only,
        "n_face_only": face_only,
        "n_weak": weak,
        "n_unclear": unclear,
        "neck_coverage": neck_cov,
    }
    quality = measured / len(pulses)
    if neck_only >= STRONG_FAIL_MIN and neck_only * 2 >= measured:
        return [
            result(
                SPEC,
                "fail",
                f"The neck changed colour after {neck_only} of {measured} flashes but the face did not: "
                "only the face looks redrawn.",
                score=neck_only / measured,
                threshold=0.5,
                source="rule",
                quality=quality,
                features=base,
            )
        ]
    if len(lags) < params["min_pairs"]:
        return [
            abstain(
                SPEC,
                f"The echoes were too weak to compare: face and neck both answered clearly on only {len(lags)} of "
                f"{len(pulses)} flashes (need {params['min_pairs']}; {weak} more were too close to the noise).",
                quality=quality,
                features=base,
            )
        ]

    lag = float(np.median(lags))
    ratio = float(np.median(ratios)) if ratios else None
    lag_score = abs(lag - params["center_ms"]) / params["scale_ms"]
    ratio_score = 0.0
    if ratio is not None:
        excess = abs(math.log(ratio / params["ratio_center"])) - params["ratio_log_tolerance"]
        ratio_score = max(0.0, excess) / params["ratio_log_scale"]
    score = lag_score + ratio_score
    tau = float(params["tau"])
    limit = tau * params["scale_ms"]
    label = "provisional limit" if source == "bootstrap" else "limit"
    late = sum(abs(x - params["center_ms"]) > limit for x in lags)
    if score <= tau:
        status = "pass"
        reason = (
            f"Face and neck changed together: median lag {lag:+.0f} ms over {len(lags)} flashes "
            f"({label} ±{limit:.0f} ms)."
        )
    elif lag_score >= ratio_score:
        status = "fail"
        reason = f"The face lagged the neck by {lag:.0f} ms on {late} of {len(lags)} flashes ({label} ±{limit:.0f} ms)."
    else:
        status = "fail"
        reason = f"The face's colour change was {ratio:.2f}x the neck's, outside the range a real face shows."
    return [
        result(
            SPEC,
            status,
            reason,
            score=score,
            threshold=tau,
            source=source,
            quality=quality,
            features={
                **base,
                "median_lag_ms": lag,
                "amplitude_ratio": ratio,
                "lag_score": lag_score,
                "ratio_score": ratio_score,
            },
        )
    ]
