"""Thresholds per check: calibrated ones from thresholds.json (M2.6/M4.2) when present, else bootstrap.yaml."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

from pulselens.models import ThresholdSource

BOOTSTRAP = Path(__file__).with_name("bootstrap.yaml")


@cache
def _bootstrap() -> dict[str, Any]:
    with open(BOOTSTRAP, encoding="utf-8") as f:
        return yaml.safe_load(f)


class Thresholds:
    def __init__(self, values: dict[str, Any], source: ThresholdSource) -> None:
        self._values = values
        self.source: ThresholdSource = source

    @classmethod
    def bootstrap(cls) -> Thresholds:
        return cls(_bootstrap(), "bootstrap")

    @property
    def provisional(self) -> bool:
        return self.source == "bootstrap"

    @property
    def echo(self) -> dict[str, Any]:
        return self._values.get("echo") or _bootstrap()["echo"]

    def for_check(self, check_id: str, profile: str | None = None) -> tuple[dict[str, Any], ThresholdSource]:
        """Parameters for a check. Per-profile values (calibration) come later; profile is accepted now."""
        return dict(self._values.get(check_id) or _bootstrap()[check_id]), self.source
