"""M2.3 acceptance (synthetic): camera reality checks (SPEC 9.2). No real faces or camera frames."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from pulselens.analyze import build_context
from pulselens.calibration.thresholds import Thresholds
from pulselens.checks import (
    camera_duplicates,
    camera_fingerprint,
    camera_modes,
    camera_noise,
    camera_rules,
    camera_timing,
)
from pulselens.checks.base import AnalysisContext
from pulselens.vision.modes import fov_scale
from pulselens.vision.noise import NoiseAccumulator
from pulselens.vision.prnu import fingerprint

H, W = 240, 320
RNG = np.random.default_rng(7)
PATTERN = RNG.normal(0, 0.02, (H, W))  # a sensor's fixed pixel pattern (PRNU), 2%


def smooth_scene(seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    s = cv2.GaussianBlur(r.uniform(0, 1, (H, W)), (0, 0), 10)
    return (s - s.min()) / (s.max() - s.min()) * 0.5 + 0.25


def jpeg(grey: np.ndarray, q: int = 95) -> np.ndarray:
    img = np.clip(np.repeat(grey[..., None], 3, 2) * 255, 0, 255).astype(np.uint8)
    return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)


def fp_frames(pattern: bool, static: bool, n: int = 40):
    rng = np.random.default_rng(1)
    for i in range(n):
        s = smooth_scene(0 if static else i)
        yield jpeg(s * (1 + (PATTERN if pattern else 0)) + rng.normal(0, 0.01, (H, W)))


def ctx(**kw) -> AnalysisContext:
    base = {"t": np.arange(100) * 33.3, "regions": {}, "pulses": (), "thresholds": Thresholds.bootstrap()}
    return AnalysisContext(**{**base, **kw})


def one(results):
    assert len(results) == 1
    return results[0]


# --- fingerprint ------------------------------------------------------------------------------------------------


def test_a_fixed_sensor_pattern_gives_a_high_pce_and_passes() -> None:
    fp = fingerprint(fp_frames(pattern=True, static=False))
    assert fp is not None and fp.pce > 1000
    assert one(camera_fingerprint.run(ctx(fingerprint=fp))).status == "pass"


def test_no_pattern_gives_a_low_pce_and_fails() -> None:
    fp = fingerprint(fp_frames(pattern=False, static=False))
    assert fp is not None and fp.pce < 10
    r = one(camera_fingerprint.run(ctx(fingerprint=fp)))
    assert r.status == "fail" and "No stable sensor pattern" in r.reason


def test_a_static_scene_with_no_pattern_cannot_fake_one() -> None:
    fp = fingerprint(fp_frames(pattern=False, static=True))
    assert fp is not None and fp.pce < 50  # the shift test: a repeated scene leaves wide, not sharp, correlation


def test_too_few_or_too_dark_fingerprint_frames_abstain() -> None:
    assert fingerprint(fp_frames(pattern=True, static=False, n=20)) is None
    dark = (jpeg(np.full((H, W), 0.1)) for _ in range(40))
    assert fingerprint(dark) is None
    assert one(camera_fingerprint.run(ctx())).status == "abstain"


# --- noise curve ------------------------------------------------------------------------------------------------


def poisson_gaussian_frames(a: float, b: float, n: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    ramp = np.tile(np.linspace(0.05, 0.95, W), (H, 1))[..., None].repeat(3, 2)
    for _ in range(n):
        yield np.clip(ramp + rng.normal(0, 1, ramp.shape) * np.sqrt(a * ramp + b), 0, 1)


@pytest.mark.parametrize(("a", "b"), [(0.0004, 1e-5), (0.0001, 4e-5), (0.001, 0.0)])
def test_the_noise_curve_slope_is_recovered_in_linear_light(a: float, b: float) -> None:
    acc = NoiseAccumulator()
    for f in poisson_gaussian_frames(a, b):
        acc.add(f)
    curve = acc.result()
    assert curve is not None
    for c in curve.channels.values():
        assert c.slope == pytest.approx(a, rel=0.1)
        assert c.r2 > 0.9
    assert one(camera_noise.run(ctx(noise=curve))).status == "pass"


def test_video_with_no_sensor_noise_is_too_clean() -> None:
    acc = NoiseAccumulator()
    for f in poisson_gaussian_frames(0.0, 0.0):
        acc.add(f)
    r = one(camera_noise.run(ctx(noise=acc.result())))
    assert r.status == "fail" and "cleaner than any sensor" in r.reason


def test_moving_pixels_are_left_out_of_the_noise_curve() -> None:
    acc = NoiseAccumulator()
    for k, f in enumerate(poisson_gaussian_frames(0.0004, 1e-5)):
        f = f.copy()
        f[:, : W // 3] = (k % 2) * 0.9  # a third of the picture flickers between black and bright
        acc.add(f)
    curve = acc.result()
    assert curve.static_share < 0.75
    assert curve.channels["g"].slope == pytest.approx(0.0004, rel=0.15)


def test_a_flat_picture_cannot_give_a_curve() -> None:
    acc = NoiseAccumulator()
    for _ in range(30):
        acc.add(np.full((H, W, 3), 0.5))
    assert acc.result() is None
    assert one(camera_noise.run(ctx())).status == "abstain"


# --- mode switch ------------------------------------------------------------------------------------------------


def textured(seed: int = 3, w: int = 640, h: int = 480) -> np.ndarray:
    r = np.random.default_rng(seed)
    img = (cv2.GaussianBlur(r.uniform(0, 255, (h, w)), (0, 0), 1.5)).astype(np.uint8)
    for _ in range(60):
        x, y = int(r.integers(0, w)), int(r.integers(0, h))
        cv2.rectangle(
            img, (x, y), (x + int(r.integers(5, 40)), y + int(r.integers(5, 40))), int(r.integers(0, 255)), -1
        )
    return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)


@pytest.mark.parametrize("crop", [0.8, 0.9])
def test_orb_estimates_a_known_crop_within_5_percent(crop: float) -> None:
    before = textured()
    h, w = before.shape[:2]
    ch, cw = int(h * crop), int(w * crop)
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    after = cv2.resize(before[y0 : y0 + ch, x0 : x0 + cw], (w, h), interpolation=cv2.INTER_AREA)
    assert fov_scale(before, after) == pytest.approx(1 / crop, rel=0.05)


def test_a_frame_that_was_only_resized_keeps_scale_1() -> None:
    before = textured()
    assert fov_scale(before, cv2.resize(before, (320, 240), interpolation=cv2.INTER_AREA)) == pytest.approx(1, rel=0.05)


def test_a_blank_wall_gives_no_fov_estimate() -> None:
    blank = np.full((480, 640, 3), 128, np.uint8)
    assert fov_scale(blank, blank) is None


def row(w: int, h: int, *, ok: bool = True, matched: bool = True, **kw) -> dict:
    return {
        "request": {"width": w, "height": h, "frameRate": 30},
        "ok": ok,
        "apply_start": 1000.0,
        "apply_end": 1040.0,
        "settings_before": {"width": 640, "height": 480},
        "settings_after": {"width": w, "height": h} if ok else {"width": 640, "height": 480},
        "first_match_t": 1250.0 if matched else None,
        "missing_frames": 4,
        "fov_scale": 1.12,
        **kw,
    }


def test_a_reported_mode_change_that_never_reaches_the_frames_fails() -> None:
    r = one(camera_modes.run(ctx(probe=(row(1280, 720, matched=False), row(640, 480)))))
    assert r.status == "fail" and r.threshold_source == "rule"
    assert "1280x720" in r.reason and r.features["phantom_switches"] == 1


def test_a_camera_that_switches_for_real_passes_with_its_features() -> None:
    probe = (row(1280, 720), row(640, 480), row(1000, 750, ok=False, error="OverconstrainedError"))
    r = one(camera_modes.run(ctx(probe=probe)))
    assert r.status == "pass"
    assert r.features["accepted"] == 2 and r.features["requests"] == 3
    assert r.features["median_latency_ms"] == 250 and r.features["max_fov_change"] == pytest.approx(0.12)


def test_modes_abstain_without_a_probe_and_skip_unsupported_requests() -> None:
    assert one(camera_modes.run(ctx())).status == "abstain"
    assert (
        one(camera_modes.run(ctx(probe=({"skipped": True, "reason": "resizeMode unsupported"},)))).status == "abstain"
    )


# --- timing and duplicates --------------------------------------------------------------------------------------


def test_timing_passes_a_jittery_camera_and_fails_a_stall() -> None:
    t = np.cumsum(np.random.default_rng(0).normal(33.3, 3, 200))
    assert one(camera_timing.run(ctx(t=t))).status == "pass"
    stalled = t.copy()
    stalled[100:] += 1500
    r = one(camera_timing.run(ctx(t=stalled)))
    assert r.status == "fail" and r.features["longest_gap_ms"] > 1500
    assert one(camera_timing.run(ctx(t=t[:10]))).status == "abstain"


def test_the_duplicate_count_is_exact() -> None:
    rng = np.random.default_rng(2)
    frames, expected = [], 0
    for i in range(80):
        if i % 4 == 3:
            frames.append(frames[-1].copy())  # an exact repeat
            expected += 1
        else:
            frames.append(
                np.clip(textured(seed=i, w=160, h=120).astype(int) + rng.integers(0, 3, (120, 160, 3)), 0, 255).astype(
                    np.uint8
                )
            )
    c = build_context(
        (({"i": i, "t": 33.3 * i, "presented_frames": i}, f, None) for i, f in enumerate(frames)),
        [],
        thresholds=Thresholds.bootstrap(),
    )
    assert c.duplicates == (expected, 79)
    r = one(camera_duplicates.run(c))
    assert r.status == "fail" and r.features["repeats"] == expected


def test_a_still_but_noisy_scene_is_not_counted_as_repeats() -> None:
    rng = np.random.default_rng(4)
    base = textured(w=160, h=120).astype(int)
    frames = [np.clip(base + rng.integers(-3, 4, base.shape), 0, 255).astype(np.uint8) for _ in range(40)]
    c = build_context(
        (({"i": i, "t": 33.3 * i}, f, None) for i, f in enumerate(frames)), [], thresholds=Thresholds.bootstrap()
    )
    assert c.duplicates[0] == 0
    assert one(camera_duplicates.run(c)).status == "pass"


# --- rules: truth tables ----------------------------------------------------------------------------------------

REAL_WEBCAM = {
    "camera_label": "USB2.0 HD UVC WebCam (322e:202c)",
    "settings": {"width": 640, "height": 480, "frameRate": 30},
    "capabilities": {"exposureMode": ["continuous", "manual"]},
    "webdriver": False,
    "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics)",
    "browser": "Chrome 155",
    "os": "Windows 11",
}


class _Noise:
    def __init__(self, mid: float) -> None:
        self.noise_mid = mid


EVEN = np.arange(200) * 33.333
JITTERY = np.cumsum(np.random.default_rng(1).normal(33.3, 3, 200))
SLOW_EVEN = np.arange(200) * 66.667


@pytest.mark.parametrize(
    ("details", "t", "noise", "status"),
    [
        (REAL_WEBCAM, JITTERY, 0.007, "pass"),  # claims nothing low
        ({**REAL_WEBCAM, "settings": {"height": 480, "frameRate": 15}}, JITTERY, 0.007, "fail"),  # 30 fps vs 15
        ({**REAL_WEBCAM, "settings": {"height": 480, "frameRate": 15}}, SLOW_EVEN, 0.007, "pass"),  # 15 as claimed
        ({**REAL_WEBCAM, "camera_label": "HD Webcam", "capabilities": {}}, EVEN, 0.0005, "fail"),  # too clean+even
        ({**REAL_WEBCAM, "camera_label": "HD Webcam", "capabilities": {}}, JITTERY, 0.0005, "pass"),  # jitter
        ({**REAL_WEBCAM, "camera_label": "HD Webcam", "capabilities": {}}, EVEN, 0.007, "pass"),  # noisy
    ],
)
def test_claim_mismatch_truth_table(details, t, noise, status) -> None:
    r = one(camera_rules.claim_mismatch(ctx(details=details, t=t, noise=_Noise(noise))))
    assert r.status == status, r.reason
    if status == "fail":
        assert r.features["force_agent"] == 1.0


@pytest.mark.parametrize(
    ("patch", "status"),
    [
        ({}, "pass"),
        ({"webdriver": True}, "fail"),
        ({"webgl_renderer": "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))"}, "fail"),
        ({"webgl_renderer": "llvmpipe (LLVM 15.0.7, 256 bits)"}, "fail"),
        ({"os": "Android 14 sdk_gphone64_x86_64"}, "fail"),
        ({"webgl_renderer": "Brave"}, "pass"),  # hidden by Brave: not a sign, recorded as renderer_hidden
    ],
)
def test_env_truth_table(patch, status) -> None:
    r = one(camera_rules.env(ctx(details={**REAL_WEBCAM, **patch})))
    assert r.status == status, r.reason


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("USB2.0 HD UVC WebCam (322e:202c)", "pass"),
        ("Integrated Camera", "pass"),
        ("OBS Virtual Camera", "fail"),
        ("ManyCam Virtual Webcam", "fail"),
        ("DroidCam Source 3", "fail"),
        ("Snap Camera", "fail"),
        ("e2eSoft iVCam", "fail"),
    ],
)
def test_label_truth_table(name, status) -> None:
    assert one(camera_rules.label(ctx(details={**REAL_WEBCAM, "camera_label": name}))).status == status


@pytest.mark.parametrize(
    "check",
    [
        camera_modes.run,
        camera_noise.run,
        camera_fingerprint.run,
        camera_timing.run,
        camera_duplicates.run,
        camera_rules.claim_mismatch,
        camera_rules.env,
        camera_rules.label,
    ],
)
def test_camera_checks_never_throw_on_bad_input(check) -> None:
    bad = [
        ctx(t=np.array([])),
        ctx(details={"settings": "nonsense", "capabilities": 5, "camera_label": None}),
        ctx(probe=({"ok": True, "settings_after": {"width": "x"}, "apply_start": "soon"}, 7)),
        ctx(t=np.full(100, np.nan)),
    ]
    for c in bad:
        r = one(check(c))
        assert r.status in ("pass", "fail", "abstain") and r.reason
