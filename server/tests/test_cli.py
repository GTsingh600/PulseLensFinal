"""M1.5 acceptance: `cli analyze` runs on a synthetic bundle and on an e2e-shaped bundle without crashing."""

import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from pulselens import cli
from pulselens.config import MODELS_DIR
from tests.fixtures.synth import light_session, write_bundle


def checks_by_id(bundle: Path) -> dict[str, dict]:
    return {c["check_id"]: c for c in json.loads((bundle / "analysis" / "checks.json").read_text())["checks"]}


def test_cli_on_a_synthetic_bundle(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path, light_session(delay_ms=150, seed=3))
    assert cli.main(["analyze", str(bundle), "--plots"]) == 0
    checks = checks_by_id(bundle)
    assert checks["optical.light.delay"]["status"] == "pass"
    assert abs(checks["optical.light.delay"]["features"]["median_ms"] - 150) <= 34
    assert checks["optical.face_neck"]["status"] == "pass"
    plots = sorted(p.name for p in (bundle / "analysis" / "plots").iterdir())
    assert "light_delay.png" in plots
    assert sum(p.startswith("echo_") for p in plots) == 6


def test_cli_flags_a_synthetic_live_swap(tmp_path: Path) -> None:
    bundle = write_bundle(tmp_path, light_session(delay_ms=120, face_lag_ms=100, seed=4))
    assert cli.main(["analyze", str(bundle)]) == 0
    assert checks_by_id(bundle)["optical.face_neck"]["status"] == "fail"


def _e2e_like_bundle(root: Path) -> Path:
    """Shaped like the Playwright e2e bundle: Chromium's fake camera (no face), real pulse log, no landmarks cache."""
    s = light_session(seed=5)
    bundle = root / "e2e-like"
    (bundle / "frames").mkdir(parents=True)
    rng = np.random.default_rng(0)
    lines = []
    for i, t in enumerate(s.t[:120]):
        img = np.zeros((480, 640, 3), np.uint8)
        img[:] = (0, 128, 0)
        cv2.circle(img, (320 + int(20 * np.sin(i / 5)), 240), 90, (60, 255, 60), -1)
        img = np.clip(img + rng.integers(0, 4, img.shape), 0, 255).astype(np.uint8)
        cv2.imwrite(str(bundle / "frames" / f"{i:06d}.jpg"), img)
        lines.append(
            {
                "i": i,
                "t": float(t),
                "capture_time": float(t),
                "presented_frames": i + 2,
                "w": 640,
                "h": 480,
                "file": f"{i:06d}.jpg",
                "fp_file": None,
            }
        )
    (bundle / "frames.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (bundle / "pulses.jsonl").write_text("".join(json.dumps(p) + "\n" for p in s.pulses))
    (bundle / "meta.json").write_text(
        json.dumps({"session_id": "e2e-like", "camera_details": {"channel": "desktop_browser"}})
    )
    return bundle


@pytest.mark.skipif(not (MODELS_DIR / "mediapipe/face_landmarker.task").exists(), reason="run `make setup` for models")
def test_cli_on_an_e2e_shaped_bundle_without_faces(tmp_path: Path) -> None:
    bundle = _e2e_like_bundle(tmp_path)
    assert cli.main(["analyze", str(bundle), "--plots"]) == 0
    checks = checks_by_id(bundle)
    assert {c["status"] for c in checks.values()} == {"abstain"}  # no face: never a fail
    assert (bundle / "landmarks.jsonl").exists()  # cached for the next run


E2E_BUNDLE = os.environ.get("PULSE_E2E_BUNDLE")


@pytest.mark.skipif(not E2E_BUNDLE, reason="set PULSE_E2E_BUNDLE to a bundle written by `make e2e`")
def test_cli_on_a_real_e2e_bundle() -> None:
    assert cli.main(["analyze", E2E_BUNDLE, "--plots"]) == 0


def test_cli_reports_a_missing_bundle(tmp_path: Path) -> None:
    assert cli.main(["analyze", str(tmp_path / "nope")]) == 2
