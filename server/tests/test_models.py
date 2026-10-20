import pytest
from pydantic import ValidationError

from pulselens.models import CheckResult, Event


def abstain(**overrides: object) -> CheckResult:
    fields: dict[str, object] = dict(
        check_id="optical.face_neck", unit="light", family="optical", status="abstain",
        score=None, threshold=None, threshold_source=None, band=None, quality=0.2, features={},
        reason="The neck was out of frame on 9 of 10 pulses.", explainer="check.optical.face_neck", plot=None,
    )
    return CheckResult(**{**fields, **overrides})


def test_check_result_round_trip() -> None:
    r = abstain()
    assert r.evidence_frames == []
    assert CheckResult.model_validate_json(r.model_dump_json()) == r


def test_check_result_rejects_unknown_family() -> None:
    with pytest.raises(ValidationError):
        abstain(family="vibes")


def test_event_serialises_every_field() -> None:
    e = Event(seq=0, t_server=1.0, type="session.created", payload={"mode": "live"})
    assert e.model_dump() == {"seq": 0, "t_server": 1.0, "t_client": None, "type": "session.created",
                              "payload": {"mode": "live"}}
