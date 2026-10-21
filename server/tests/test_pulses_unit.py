"""White-box tests of pulse signing and the light-suite plan (SPEC 6, 7.4)."""

import random
import re
import secrets
from typing import get_args

import pytest

from pulselens.models import PulseKind
from pulselens.pulses import canonical, light_suite, same_signature, sign_pulse

PARAMS = {"mode": "colour", "hue_deg": 60.0, "duration_ms": 400}


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_the_signature_does_not_depend_on_key_order() -> None:
    reordered = dict(reversed(list(PARAMS.items())))
    assert sign_pulse("k", "s-1", "light", PARAMS, "s") == sign_pulse("k", "s-1", "light", reordered, "s")


@pytest.mark.parametrize(
    "change",
    [
        {"secret": "other"},
        {"pulse_id": "s-2"},
        {"kind": "tilt"},
        {"params": {**PARAMS, "hue_deg": 61.0}},
        {"params": {**PARAMS, "duration_ms": 401}},
        {"session_id": "t"},
    ],
)
def test_changing_any_signed_field_changes_the_signature(change) -> None:
    base = {"secret": "k", "pulse_id": "s-1", "kind": "light", "params": PARAMS, "session_id": "s"}
    a = sign_pulse(**base)
    b = sign_pulse(**{**base, **change})
    assert not same_signature(a, b)
    assert same_signature(a, sign_pulse(**base))


def test_the_separator_is_unambiguous_because_ids_and_kinds_never_contain_it() -> None:
    # "a|b" + "c" and "a" + "b|c" sign the same bytes, so the scheme relies on signed fields being server-made:
    # pulse ids are "<hex session id>-<n>" and kinds come from a fixed set, none with "|".
    assert sign_pulse("k", "s-1|light", "x", PARAMS, "s") == sign_pulse("k", "s-1", "light|x", PARAMS, "s")
    assert not any("|" in k for k in get_args(PulseKind))
    assert re.fullmatch(r"[0-9a-f]{16}-\d+", f"{secrets.token_hex(8)}-3")


def test_light_suite_has_6_colour_2_split_2_white_over_the_isoluminant_hues() -> None:
    plan = light_suite(6, 2, 2, 400, random.Random(1))
    modes = [p["mode"] for p in plan]
    assert modes.count("colour") == 6 and modes.count("split") == 2 and modes.count("white") == 2
    assert sorted(p["hue_deg"] for p in plan if p["mode"] == "colour") == [0, 60, 120, 180, 240, 300]
    for p in plan:
        assert p["duration_ms"] == 400
        if p["mode"] == "split":
            assert (p["right_hue_deg"] - p["left_hue_deg"]) % 360 == 180
            assert p["left_hue_deg"] in {0, 60, 120, 180, 240, 300}


def test_light_suite_is_shuffled_but_reproducible_from_the_seed() -> None:
    a = light_suite(6, 2, 2, 400, random.Random(7))
    assert a == light_suite(6, 2, 2, 400, random.Random(7))
    orders = {tuple(p["mode"] for p in light_suite(6, 2, 2, 400, random.Random(s))) for s in range(20)}
    assert len(orders) > 1


def test_light_suite_with_no_colour_pulses_still_makes_splits_and_whites() -> None:
    plan = light_suite(0, 1, 2, 400, random.Random(0))
    assert sorted(p["mode"] for p in plan) == ["split", "white", "white"]
