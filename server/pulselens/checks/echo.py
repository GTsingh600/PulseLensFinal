"""Echo onset, the shared helper of the optical family (SPEC 9.3).

1. Chromaticity x = RGB / sum(RGB) of the region's mean linear colour.
2. Expected direction d = the pulse colour's chromaticity minus neutral (1/3, 1/3, 1/3), as a unit vector.
3. Projection p(t) = (x(t) - mean of x over the 300 ms before `painted`) · d.
4. Onset = the first two consecutive frames above max(4 σ_pre, a_min) within 700 ms of `painted`,
   interpolated linearly to the threshold crossing.

Pure: frame times, one region's series and one pulse in; an EchoOnset out. Never raises on bad data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pulselens.checks.base import Pulse, RegionSeries

BASELINE_MS = 300.0
WINDOW_MS = 700.0
K_SIGMA = 4.0
NO_ECHO_MS = 1000.0  # what light.delay counts for a pulse with no echo
MIN_BASELINE_FRAMES = 3
MIN_COVERAGE = 0.5  # a frame counts for a region when at least this much of it is in view
MIN_WINDOW_SHARE = 0.8  # share of the window's frames that must be usable


@dataclass
class EchoOnset:
    pulse_id: str
    region: str
    valid: bool  # enough clean frames to judge; an invalid pulse is left out, not counted as "no echo"
    onset_ms: float | None = None  # after `painted`; None = no echo
    amplitude: float | None = None  # projection reached during the pulse
    threshold: float | None = None
    sigma_pre: float | None = None
    reason: str | None = None
    t_rel: np.ndarray = field(default_factory=lambda: np.empty(0))  # for plots: time after painted, ms
    p: np.ndarray = field(default_factory=lambda: np.empty(0))  # for plots: projection


def chromaticity(rgb: np.ndarray) -> np.ndarray:
    s = rgb.sum(axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, rgb / s, np.nan)


def direction(colour: np.ndarray) -> np.ndarray | None:
    d = chromaticity(np.asarray(colour, dtype=np.float64)) - 1.0 / 3.0
    n = float(np.linalg.norm(d))
    return d / n if np.isfinite(n) and n > 1e-6 else None


def echo_onset(
    t: np.ndarray,
    series: RegionSeries,
    pulse: Pulse,
    colour: np.ndarray | None = None,
    *,
    region: str = "",
    a_min: float = 0.003,
) -> EchoOnset:
    out = EchoOnset(pulse_id=pulse.pulse_id, region=region, valid=False)
    colour = pulse.colour if colour is None else colour
    d = direction(colour) if colour is not None else None
    if pulse.painted is None or d is None:
        out.reason = "no painted time or no colour direction"
        return out
    t = np.asarray(t, dtype=np.float64)
    if len(t) == 0 or len(series.rgb) != len(t):
        out.reason = "no frames"
        return out
    painted = pulse.painted
    duration = (pulse.ended - painted) if pulse.ended is not None else float(pulse.params.get("duration_ms", 400))
    x = chromaticity(series.rgb)
    usable = (series.coverage >= MIN_COVERAGE) & np.isfinite(x).all(axis=1)

    base = usable & (t >= painted - BASELINE_MS) & (t < painted)
    if base.sum() < MIN_BASELINE_FRAMES:
        out.reason = f"{int(base.sum())} usable baseline frames"
        return out
    in_window = (t >= painted) & (t <= painted + WINDOW_MS)
    if not in_window.any() or usable[in_window].mean() < MIN_WINDOW_SHARE:
        out.reason = "region not visible during the pulse"
        return out

    p = (x - x[base].mean(axis=0)) @ d
    sigma = float(np.std(p[base], ddof=1))
    thr = max(K_SIGMA * sigma, a_min)
    span = usable & (t >= painted - BASELINE_MS) & (t <= painted + WINDOW_MS + duration)
    out.valid, out.threshold, out.sigma_pre = True, thr, sigma
    out.t_rel, out.p = t[span] - painted, p[span]

    idx = np.flatnonzero(usable & in_window)
    for a, b in zip(idx[:-1], idx[1:], strict=False):
        if p[a] > thr and p[b] > thr:
            prev = np.flatnonzero(usable[:a])
            t_cross = t[a]
            if len(prev) and p[prev[-1]] < thr:
                k = prev[-1]
                t_cross = t[k] + (thr - p[k]) / (p[a] - p[k]) * (t[a] - t[k])
            out.onset_ms = float(t_cross - painted)
            hold = usable & (t >= t_cross + 0.25 * duration) & (t <= t_cross + 0.75 * duration)
            out.amplitude = float(np.median(p[hold])) if hold.any() else float(p[a : b + 1].max())
            break
    return out
