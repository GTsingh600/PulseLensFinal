"""Check registry (CLAUDE.md): every check module registers its family, unit, explainer key and plot type here.

The planner (M3.1, track C) reads units and families from this table; the analysis runs every registered check.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pulselens.models import Family

if TYPE_CHECKING:
    from pulselens.checks.base import AnalysisContext
    from pulselens.models import CheckResult


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    family: Family
    unit: str  # planning unit (SPEC 11): camera, light, tilt, hand, lens, clip, physiology
    explainer: str  # key in docs/EXPLAINERS.md
    plot: str  # echo, split, tilt, noise, modes, continuity


RunFn = Callable[["AnalysisContext"], "list[CheckResult]"]
REGISTRY: dict[str, tuple[CheckSpec, RunFn]] = {}

# Modules that register checks; each new check module is added here.
CHECK_MODULES = (
    "pulselens.checks.camera_modes",
    "pulselens.checks.camera_noise",
    "pulselens.checks.camera_fingerprint",
    "pulselens.checks.camera_timing",
    "pulselens.checks.camera_duplicates",
    "pulselens.checks.camera_rules",
    "pulselens.checks.optical_light",
    "pulselens.checks.optical_face_neck",
)


def register(spec: CheckSpec) -> Callable[[RunFn], RunFn]:
    def deco(run: RunFn) -> RunFn:
        REGISTRY[spec.check_id] = (spec, run)
        return run

    return deco


def load_all() -> dict[str, tuple[CheckSpec, Any]]:
    for name in CHECK_MODULES:
        importlib.import_module(name)
    return REGISTRY
