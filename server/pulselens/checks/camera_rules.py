"""Camera rules (SPEC 9.2): claim_mismatch, env and label, from camera_details and the measured video.

- camera.claim_mismatch: the device claims low quality (frame rate ≤ 20, or ≤ 480p with a generic name and no
  controls) but sends video that is perfectly clean and perfectly even, or faster than 1.2x the claim. An attacker
  posing as a cheap webcam to get easier checks. Sets force_agent.
- camera.env (weak): automation (navigator.webdriver), a software renderer (SwiftShader, llvmpipe) or an emulator.
- camera.label (weak): the camera calls itself a known virtual camera. Trivially renamed, so it catches lazy tries.
Weak rules never decide alone; fusion (M3.2) weighs them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pulselens.checks.base import AnalysisContext, abstain, guarded, result
from pulselens.checks.camera_timing import timing_features
from pulselens.models import CheckResult
from pulselens.planner.registry import CheckSpec, register

CLAIM = CheckSpec("camera.claim_mismatch", "camera", "camera", "check.camera.claim_mismatch", "modes")
ENV = CheckSpec("camera.env", "camera", "camera", "check.camera.env", "modes")
LABEL = CheckSpec("camera.label", "camera", "camera", "check.camera.label", "modes")

VIRTUAL_CAMERAS = re.compile(
    r"obs|manycam|snap camera|xsplit|droidcam|iriun|e2esoft|camtwist|mmhmm|virtual|vcam|splitcam|youcam|epoccam",
    re.IGNORECASE,
)
SOFTWARE_RENDERER = re.compile(r"swiftshader|llvmpipe|softpipe|software rasterizer|virtualbox|vmware", re.IGNORECASE)
EMULATOR = re.compile(r"sdk_gphone|android sdk built for|emulator|genymotion|bluestacks", re.IGNORECASE)
GENERIC_LABEL = re.compile(r"^\s*(?:$|(?:usb|hd|integrated|web|front|user)?\s*(?:camera|webcam|cam)\b)", re.IGNORECASE)
CONTROLS = ("exposureMode", "exposureTime", "whiteBalanceMode", "colorTemperature", "focusMode", "zoom", "torch")


def _settings(details: Mapping[str, Any]) -> Mapping[str, Any]:
    s = details.get("settings")
    return s if isinstance(s, Mapping) else {}


@register(CLAIM)
@guarded(CLAIM)
def claim_mismatch(ctx: AnalysisContext) -> list[CheckResult]:
    d = ctx.details
    if not d:
        return [abstain(CLAIM, "No camera details in this session.")]
    params, _ = ctx.thresholds.for_check(CLAIM.check_id, ctx.profile)
    s = _settings(d)
    claimed_fps = s.get("frameRate") if isinstance(s.get("frameRate"), int | float) else None
    caps = d.get("capabilities") if isinstance(d.get("capabilities"), Mapping) else {}
    generic = bool(GENERIC_LABEL.match(str(d.get("camera_label") or "")))
    low_res = isinstance(s.get("height"), int | float) and s["height"] <= 480
    no_controls = not any(k in caps for k in CONTROLS)
    claims_low = (claimed_fps is not None and claimed_fps <= 20) or (low_res and generic and no_controls)
    timing = timing_features(ctx.t)
    noise_mid = ctx.noise.noise_mid if ctx.noise else None
    features: dict[str, Any] = {
        "claimed_fps": claimed_fps,
        "claims_low": float(claims_low),
        "measured_fps": timing["fps"] if timing else None,
        "timing_cv": timing["cv"] if timing else None,
        "noise_mid": noise_mid,
    }
    if not claims_low:
        return [
            result(
                CLAIM,
                "pass",
                "The device does not claim a low-quality camera.",
                source="rule",
                quality=1.0,
                features=features,
            )
        ]
    if timing is None:
        return [abstain(CLAIM, "Too few frames to compare the claim with the video.", features=features)]
    too_clean = (
        noise_mid is not None
        and noise_mid < float(params["low_noise_mid"])
        and timing["cv"] < float(params["low_timing_cv"])
    )
    too_fast = claimed_fps is not None and timing["fps"] > float(params["fps_over_claim"]) * claimed_fps
    if too_clean or too_fast:
        why = "perfectly clean, perfectly even video" if too_clean else f"{timing['fps']:.0f} fps"
        return [
            result(
                CLAIM,
                "fail",
                f"It claims a basic camera but sends {why}; the plan gets stricter and an agent checks.",
                source="rule",
                quality=1.0,
                features={**features, "force_agent": 1.0},
            )
        ]
    return [
        result(
            CLAIM,
            "pass",
            "The video matches the basic camera the device claims.",
            source="rule",
            quality=1.0,
            features=features,
        )
    ]


@register(ENV)
@guarded(ENV)
def env(ctx: AnalysisContext) -> list[CheckResult]:
    d = ctx.details
    if not d:
        return [abstain(ENV, "No camera details in this session.")]
    signs = []
    if d.get("webdriver"):
        signs.append("browser automation (webdriver)")
    renderer = str(d.get("webgl_renderer") or "")
    if SOFTWARE_RENDERER.search(renderer):
        signs.append(f"software graphics ({renderer})")
    if EMULATOR.search(f"{d.get('browser', '')} {d.get('os', '')} {renderer}"):
        signs.append("an emulator")
    features = {"signs": float(len(signs)), "renderer_hidden": float(renderer in ("", "Brave"))}
    if signs:
        return [
            result(
                ENV,
                "fail",
                f"Signs of {', '.join(signs)}; a weak sign that never decides alone.",
                source="rule",
                quality=1.0,
                features=features,
            )
        ]
    return [
        result(
            ENV,
            "pass",
            "No signs of automation, software graphics or an emulator.",
            source="rule",
            quality=1.0,
            features=features,
        )
    ]


@register(LABEL)
@guarded(LABEL)
def label(ctx: AnalysisContext) -> list[CheckResult]:
    name = str(ctx.details.get("camera_label") or "") if ctx.details else ""
    if not ctx.details:
        return [abstain(LABEL, "No camera details in this session.")]
    if m := VIRTUAL_CAMERAS.search(name):
        return [
            result(
                LABEL,
                "fail",
                f'The camera calls itself "{name}", a known virtual camera ({m.group(0)}).',
                source="rule",
                quality=1.0,
                features={"virtual_name": 1.0},
            )
        ]
    return [
        result(
            LABEL,
            "pass",
            "The camera's name is not a known virtual camera (easily renamed, so weak).",
            source="rule",
            quality=1.0,
            features={"virtual_name": 0.0},
        )
    ]
