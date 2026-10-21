"""camera.modes (SPEC 7.3, 9.2): what the camera did when asked to switch modes, from probe.jsonl.

Each row is one request (see SPEC 7.3 for the fields): accepted or not, how long until a frame of the new size
arrived, frames missing during the switch, and the field-of-view scale between a frame before and one after
(`fov_scale`, added by the CLI from vision/modes.py).
- Rule: the settings report the new size but no frame of that size ever arrives → fail. Software that only edits
  its settings while sending the same video does this; a real camera cannot.
- The other features are shown and compared with genuine profiles once calibrated (PROVISIONAL until then).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

SPEC = CheckSpec("camera.modes", "camera", "camera", "check.camera.modes", "modes")


def _size(settings: Any) -> tuple[int, int] | None:
    if isinstance(settings, Mapping) and isinstance(settings.get("width"), int | float) and settings.get("height"):
        return int(settings["width"]), int(settings["height"])
    return None


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, int | float) and np.isfinite(x) else None


@register(SPEC)
@guarded(SPEC)
def run(ctx: AnalysisContext) -> list[CheckResult]:
    rows = [r for r in ctx.probe if isinstance(r, Mapping) and not r.get("skipped")]
    if not rows:
        return [abstain(SPEC, "The mode-switch probe did not run in this session.")]
    params, source = ctx.thresholds.for_check(SPEC.check_id, ctx.profile)
    accepted = [r for r in rows if r.get("ok")]
    phantom = []  # settings changed, frames never did
    latencies, missing, fovs = [], [], []
    for r in accepted:
        before, after = _size(r.get("settings_before")), _size(r.get("settings_after"))
        first, start = _num(r.get("first_match_t")), _num(r.get("apply_start"))
        if after and before and after != before and first is None:
            phantom.append(f"{after[0]}x{after[1]}")
        if first is not None and start is not None:
            latencies.append(first - start)
        if (m := _num(r.get("missing_frames"))) is not None:
            missing.append(m)
        if (s := _num(r.get("fov_scale"))) is not None:
            fovs.append(s)
    unusual = [r for r in accepted if r.get("unusual")]
    tol = float(params["fov_tolerance"])
    features = {
        "requests": len(rows),
        "accepted": len(accepted),
        "unusual_accepted": len(unusual),
        "median_latency_ms": float(np.median(latencies)) if latencies else None,
        "median_missing_frames": float(np.median(missing)) if missing else None,
        "max_fov_change": float(max(abs(s - 1) for s in fovs)) if fovs else None,
        "phantom_switches": len(phantom),
    }
    if phantom:
        return [
            result(
                SPEC,
                "fail",
                f"The camera reported switching to {', '.join(phantom)} but no frame of that size ever arrived.",
                score=float(len(phantom)),
                threshold=0.0,
                source="rule",
                quality=1.0,
                features=features,
            )
        ]
    moved = features["max_fov_change"] is not None and features["max_fov_change"] > tol
    latency = features["median_latency_ms"]
    reason = (
        f"Accepted {len(accepted)} of {len(rows)} mode requests"
        + (f", switching in {latency:.0f} ms" if latency is not None else "")
        + (", and the view shifted" if moved else ", view unchanged" if fovs else "")
        + "; compared with genuine cameras once calibrated."
    )
    return [result(SPEC, "pass", reason, source=source, quality=len(accepted) / len(rows), features=features)]
