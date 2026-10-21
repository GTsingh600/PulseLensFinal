"""Pulse signing and the light-suite plan (SPEC 6, 7.4).

Pulses are signed with HMAC_SHA256(secret, pulse_id|kind|params|session_id), where params is canonical JSON
(sorted keys, no spaces), so the signature does not depend on how a dict happened to be ordered.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
from typing import Any

from pulselens.models import LightParams


def canonical(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def sign_pulse(secret: str, pulse_id: str, kind: str, params: dict[str, Any], session_id: str) -> str:
    message = f"{pulse_id}|{kind}|{canonical(params)}|{session_id}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def same_signature(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def light_suite(colour: int, split: int, white: int, duration_ms: int, rng: random.Random) -> list[dict[str, Any]]:
    """Light-suite params, shuffled: colour pulses over the isoluminant hues (0, 60, ...), split pairs of opposite
    hues from the same set, and white pulses. The client turns hues into colours and reports what it painted."""
    hues = [360.0 * k / colour for k in range(colour)] if colour else [0.0]
    plan = [LightParams(mode="colour", hue_deg=h, duration_ms=duration_ms) for h in hues[:colour]]
    for k in range(split):
        left = hues[(2 * k) % len(hues)]
        plan.append(
            LightParams(mode="split", left_hue_deg=left, right_hue_deg=(left + 180) % 360, duration_ms=duration_ms)
        )
    plan += [LightParams(mode="white", duration_ms=duration_ms) for _ in range(white)]
    rng.shuffle(plan)
    return [p.model_dump() for p in plan]
