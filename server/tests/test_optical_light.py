"""M1.5 acceptance (synthetic): light echo timing and face-vs-neck."""

import numpy as np
import pytest

from pulselens.calibration.thresholds import Thresholds
from pulselens.checks import optical_face_neck, optical_light
from pulselens.checks.base import AnalysisContext, RegionSeries
from pulselens.checks.echo import echo_onset
from tests.fixtures.synth import light_session


def ctx(s, **kw) -> AnalysisContext:
    return AnalysisContext(
        t=s.t, regions=s.regions, pulses=tuple(s.pulse_objs), thresholds=Thresholds.bootstrap(), **kw
    )


def one(results):
    assert len(results) == 1
    return results[0]


@pytest.mark.parametrize("fps", [30.0, 24.0])
@pytest.mark.parametrize("delay", [60, 100, 150, 250])
def test_light_delay_is_recovered_within_one_frame(delay: int, fps: float) -> None:
    s = light_session(delay_ms=delay, fps=fps, seed=delay)
    frame = 1000 / fps
    onsets = [echo_onset(s.t, s.regions["skin"], p) for p in s.pulse_objs if p.mode == "colour"]
    assert all(o.valid and o.onset_ms is not None for o in onsets)
    for o in onsets:
        assert abs(o.onset_ms - delay) <= frame, (o.pulse_id, o.onset_ms)
    r = one(optical_light.run(ctx(s)))
    assert abs(r.features["median_ms"] - delay) <= frame
    assert r.features["n_valid"] == 6 and r.features["n_echo"] == 6


def test_light_delay_passes_genuine_and_fails_a_replay_with_no_echo() -> None:
    genuine = one(optical_light.run(ctx(light_session(delay_ms=120))))
    assert genuine.status == "pass"
    assert genuine.check_id == "optical.light.delay" and genuine.family == "optical" and genuine.unit == "light"
    assert genuine.explainer == "check.optical.light.delay"
    assert genuine.threshold_source == "bootstrap"
    replay = one(optical_light.run(ctx(light_session(face_echo=False, neck_echo=False))))
    assert replay.status == "fail"
    assert replay.features["n_echo"] == 0 and replay.features["median_ms"] == 1000
    assert "0 of 6" in replay.reason


def test_light_delay_abstains_without_a_face() -> None:
    r = one(optical_light.run(ctx(light_session(face_present=False))))
    assert r.status == "abstain"
    assert r.score is None


def test_face_neck_passes_when_face_and_neck_echo_together() -> None:
    r = one(optical_face_neck.run(ctx(light_session(delay_ms=150))))
    assert r.status == "pass", r.reason
    assert abs(r.features["median_lag_ms"]) < 20
    assert r.features["n_pairs"] == 6


def test_face_lagging_neck_by_100ms_is_detected() -> None:
    r = one(optical_face_neck.run(ctx(light_session(delay_ms=120, face_lag_ms=100))))
    assert r.status == "fail", r.reason
    assert r.features["median_lag_ms"] == pytest.approx(100, abs=34)
    assert "lagged the neck" in r.reason


def test_neck_echo_with_no_face_echo_is_a_strong_fail() -> None:
    r = one(optical_face_neck.run(ctx(light_session(face_echo=False))))
    assert r.status == "fail"
    assert r.threshold_source == "rule"
    assert r.features["n_neck_only"] == 6
    assert "neck" in r.reason and "face" in r.reason


def test_neck_out_of_frame_abstains() -> None:
    r = one(optical_face_neck.run(ctx(light_session(neck_coverage=0.0))))
    assert r.status == "abstain"
    assert "out of frame" in r.reason


def test_saturated_neck_abstains() -> None:
    s = light_session()
    s.regions["neck"] = RegionSeries(
        rgb=np.full_like(s.regions["neck"].rgb, 0.995), coverage=s.regions["neck"].coverage
    )
    r = one(optical_face_neck.run(ctx(s)))
    assert r.status == "abstain"
    assert "saturated" in r.reason


@pytest.mark.parametrize("check", [optical_light, optical_face_neck])
def test_checks_never_throw_on_bad_input(check) -> None:
    empty = AnalysisContext(t=np.array([]), regions={}, pulses=(), thresholds=Thresholds.bootstrap())
    nan = light_session()
    nan.regions["skin"] = RegionSeries(
        rgb=np.full_like(nan.regions["skin"].rgb, np.nan), coverage=nan.regions["skin"].coverage
    )
    for c in (empty, ctx(nan)):
        r = one(check.run(c))
        assert r.status == "abstain"
        assert r.reason
