"""Frames → region means → checks. Pure: images and landmarks come in as values, nothing is read or written here."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from pulselens.calibration.thresholds import Thresholds
from pulselens.checks.base import AnalysisContext, Pulse, RegionSeries
from pulselens.models import CheckResult
from pulselens.planner.registry import load_all
from pulselens.vision.face import regions_from_landmarks, to_pixels
from pulselens.vision.frames import REGION_NAMES, region_means
from pulselens.vision.linearize import srgb_to_linear

Landmarks = Mapping[Any, Any] | None  # normalised positions by landmark index, or None (no face)


def build_context(
    frames: Iterable[tuple[Mapping[str, Any], np.ndarray | None, Landmarks]],
    pulses: Iterable[Mapping[str, Any]],
    *,
    thresholds: Thresholds,
    profile: str | None = None,
    quality_min: float = 0.5,
) -> AnalysisContext:
    """frames: (frames.jsonl line, RGB uint8 image or None, landmarks or None) in capture order."""
    times: list[float] = []
    acc: dict[str, list[np.ndarray]] = {n: [] for n in REGION_NAMES}
    cov: dict[str, list[float]] = {n: [] for n in REGION_NAMES}
    for meta, image, lm in frames:
        if image is None:
            continue
        h, w = image.shape[:2]
        linear = srgb_to_linear(image)
        regions = regions_from_landmarks(to_pixels(lm, w, h), w, h) if lm else None
        for name, (mean, coverage) in region_means(linear, regions).items():
            acc[name].append(mean)
            cov[name].append(coverage)
        times.append(float(meta["t"]))
    regions_series = {
        n: RegionSeries(rgb=np.array(acc[n]).reshape(-1, 3), coverage=np.array(cov[n], dtype=np.float64))
        for n in REGION_NAMES
    }
    return AnalysisContext(
        t=np.array(times, dtype=np.float64),
        regions=regions_series,
        pulses=tuple(Pulse.from_log(p) for p in pulses),
        thresholds=thresholds,
        profile=profile,
        quality_min=quality_min,
    )


def run_checks(ctx: AnalysisContext) -> list[CheckResult]:
    out: list[CheckResult] = []
    for _spec, run in load_all().values():
        out.extend(run(ctx))
    return out
