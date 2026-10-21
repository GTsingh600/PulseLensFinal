"""Optical checks across the conditions a real laptop or phone produces (synthetic).

A genuine session must never fail: it may pass or abstain. The matrix covers frame rates down to the 12 fps floor
of SPEC 7.6, a neck or shirt that answers the screen weaker or stronger than the face (within the 4x the check
allows), a rolling shutter that reads the neck rows after the face rows, and sensor noise up to a dim webcam's.
"""

import itertools

import pytest

from pulselens.calibration.thresholds import Thresholds
from pulselens.checks import optical_face_neck, optical_light
from pulselens.checks.base import AnalysisContext
from tests.fixtures.synth import light_session

FPS = [12.0, 15.0, 20.0, 24.0, 30.0]
NECK_GAIN = [0.3, 1.0, 3.0]
NECK_LEAD_FRAMES = [0.0, 0.3]
NOISE = [0.0006, 0.0015, 0.003]
SEEDS = range(12)


def ctx(s) -> AnalysisContext:
    return AnalysisContext(t=s.t, regions=s.regions, pulses=tuple(s.pulse_objs), thresholds=Thresholds.bootstrap())


def session(fps: float, gain: float, lead: float, noise: float, seed: int, **kw):
    return light_session(
        fps=fps, neck_gain=gain, neck_lead_ms=lead * 1000 / fps, noise=noise, jitter_ms=4.0, seed=seed, **kw
    )


GENUINE = list(itertools.product(FPS, NECK_GAIN, NECK_LEAD_FRAMES, NOISE))


@pytest.mark.parametrize(("fps", "gain", "lead", "noise"), GENUINE)
def test_a_genuine_face_never_fails_face_vs_neck(fps: float, gain: float, lead: float, noise: float) -> None:
    fails = []
    for seed in SEEDS:
        r = optical_face_neck.run(ctx(session(fps, gain, lead, noise, seed)))[0]
        if r.status == "fail":
            fails.append((seed, r.features.get("median_lag_ms"), r.reason))
    assert not fails, fails


@pytest.mark.parametrize(("fps", "gain", "lead", "noise"), GENUINE)
def test_a_genuine_face_never_fails_light_delay(fps: float, gain: float, lead: float, noise: float) -> None:
    for seed in SEEDS:
        r = optical_light.run(ctx(session(fps, gain, lead, noise, seed)))[0]
        assert r.status != "fail", (seed, r.reason)


LAGGED = list(itertools.product([20.0, 24.0, 30.0], NECK_GAIN, NECK_LEAD_FRAMES, NOISE))


@pytest.mark.parametrize(("fps", "gain", "lead", "noise"), LAGGED)
def test_a_face_redrawn_100ms_late_never_passes(fps: float, gain: float, lead: float, noise: float) -> None:
    """At 20 fps and up a 100 ms lag never passes. With a neck echo as strong as the face's and moderate noise it
    always fails; a weak neck near the noise may abstain instead (the SNR gate), which sends it to the agent."""
    statuses = []
    for seed in SEEDS:
        r = optical_face_neck.run(ctx(session(fps, gain, lead, noise, seed, face_lag_ms=100.0)))[0]
        statuses.append(r.status)
    assert "pass" not in statuses, statuses
    if noise <= 0.0015 and gain >= 1.0:
        assert statuses.count("fail") == len(SEEDS), statuses


@pytest.mark.parametrize("fps", [8.0, 10.0, 11.5])
@pytest.mark.parametrize("check", [optical_light, optical_face_neck])
def test_below_12fps_the_optical_checks_abstain(check, fps: float) -> None:
    r = check.run(ctx(light_session(fps=fps, seed=1)))[0]
    assert r.status == "abstain", r.reason
    assert "fps" in r.reason or "frame rate" in r.reason
