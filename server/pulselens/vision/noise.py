"""Temporal noise curve (SPEC 9.2, camera.noise_curve). Pure: linear frames in, a fitted curve out.

For every 3rd frame pair: pixels that did not move (blurred difference below a threshold) give temporal noise
d = (g_t - g_t-1) / sqrt(2) at brightness mu = (g_t + g_t-1) / 2. Samples are binned by mu (12 bins, at least 200
pixels each); each bin's variance comes from the MAD (robust to the few pixels that did move), and
var = a * mu + b is fitted per channel by least squares weighted by the pixel count. Bins within 3 sigma of black or
white are left out: clipping there shrinks the spread.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

N_BINS = 12
MIN_PER_BIN = 200
MIN_BINS = 6
STATIC_DIFF = 0.02  # smallest blurred |difference| (linear light) that counts as movement
SAMPLES_PER_PAIR = 6000  # per channel, so a long session stays small in memory
PAIR_EVERY = 3


@dataclass
class ChannelFit:
    slope: float  # a
    intercept: float  # b
    r2: float
    noise_mid: float  # sigma at mu = 0.5 from the fit (0 when the fit goes negative)
    bins: list[tuple[float, float, int]]  # (mu, variance, n) per bin used


@dataclass
class NoiseCurve:
    channels: dict[str, ChannelFit]
    pairs: int
    static_share: float  # mean share of static pixels over the pairs used

    @property
    def noise_mid(self) -> float:
        return float(np.median([c.noise_mid for c in self.channels.values()]))


@dataclass
class NoiseAccumulator:
    """Feed frames in capture order with `add`; `result` fits the curve (None when there is too little to fit)."""

    seed: int = 0
    _prev: np.ndarray | None = None
    _k: int = 0
    _mu: list[np.ndarray] = field(default_factory=list)
    _d: list[np.ndarray] = field(default_factory=list)
    _static: list[float] = field(default_factory=list)

    def add(self, linear: np.ndarray) -> None:
        cur = np.asarray(linear, dtype=np.float32)
        prev, self._prev = self._prev, cur
        self._k += 1
        if prev is None or prev.shape != cur.shape or (self._k - 2) % PAIR_EVERY:
            return
        diff = cv2.GaussianBlur(cur, (5, 5), 0) - cv2.GaussianBlur(prev, (5, 5), 0)
        # Noise itself moves the blurred difference a little; a fixed cut would drop the noisiest still pixels and
        # bias the curve down, so the cut is 4 robust sigmas of the difference (never below STATIC_DIFF).
        spread = 1.4826 * float(np.median(np.abs(diff)))
        moved = np.abs(diff).max(axis=2)
        static = moved < max(STATIC_DIFF, 4 * spread)
        self._static.append(float(static.mean()))
        idx = np.flatnonzero(static.ravel())
        if len(idx) < MIN_PER_BIN:
            return
        rng = np.random.default_rng(self.seed + self._k)
        idx = rng.choice(idx, size=min(len(idx), SAMPLES_PER_PAIR), replace=False)
        a, b = prev.reshape(-1, 3)[idx], cur.reshape(-1, 3)[idx]
        self._mu.append((a + b) / 2)
        self._d.append((b - a) / np.sqrt(2))

    def result(self) -> NoiseCurve | None:
        if not self._mu:
            return None
        mu, d = np.concatenate(self._mu), np.concatenate(self._d)
        channels = {}
        for c, name in enumerate("rgb"):
            fit = fit_channel(mu[:, c], d[:, c])
            if fit is None:
                return None
            channels[name] = fit
        return NoiseCurve(channels=channels, pairs=len(self._mu), static_share=float(np.mean(self._static)))


def fit_channel(mu: np.ndarray, d: np.ndarray) -> ChannelFit | None:
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    bins = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        sel = (mu >= lo) & (mu < hi) & (mu > 0.002) & (mu < 0.98)  # clipped pixels have no noise
        n = int(sel.sum())
        if n >= MIN_PER_BIN:
            x = d[sel]
            sigma = 1.4826 * float(np.median(np.abs(x - np.median(x))))
            centre = float(mu[sel].mean())
            if centre - 3 * sigma < 0 or centre + 3 * sigma > 1:
                continue  # pixels clip at black or white here, which shrinks the measured spread
            bins.append((centre, sigma**2, n))
    if len(bins) < MIN_BINS:
        return None
    m, v, w = (np.array(z, dtype=np.float64) for z in zip(*bins, strict=True))
    sw = np.sqrt(w)
    a, b = np.linalg.lstsq(np.stack([m, np.ones_like(m)], 1) * sw[:, None], v * sw, rcond=None)[0]
    pred = a * m + b
    ss_res, ss_tot = float(np.sum(w * (v - pred) ** 2)), float(np.sum(w * (v - np.average(v, weights=w)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return ChannelFit(
        slope=float(a),
        intercept=float(b),
        r2=float(r2),
        noise_mid=float(np.sqrt(max(0.0, a * 0.5 + b))),
        bins=[(float(x), float(y), int(z)) for x, y, z in bins],
    )
