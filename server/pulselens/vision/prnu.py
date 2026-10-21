"""Sensor fingerprint (PRNU) and PCE (SPEC 9.2, camera.fingerprint). Pure: frames in, a match score out.

1. Green channel of each fingerprint frame (native size), centre crop to at most CROP x CROP.
2. Residual W = I - D(I). D is a local adaptive Wiener denoiser in the pixel domain (the role of the wavelet
   denoiser in the SPEC: keep the scene, leave the sensor's fine noise in W), so no wavelet library is needed.
3. K = sum(W * I) / sum(I^2), separately on odd and even frames.
4. Zero-mean rows and columns, and the 8x8 block-phase means (the JPEG grid every encoder leaves, camera or not).
5. PCE between the two halves: peak of the circular cross-correlation at zero shift, squared, over the mean square
   of the correlation outside a small window around it. A real sensor's pattern is white, so the peak is sharp; a
   static scene leaves smooth, wide correlation, so it can't fake a high PCE.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import cv2
import numpy as np

CROP = 512
MIN_FRAMES = 30
LUMA_RANGE = (60, 200)  # mean 8-bit luma of a usable fingerprint frame
PEAK_EXCLUDE = 5  # half-width of the window around the peak left out of the PCE denominator


@dataclass
class Fingerprint:
    pce: float
    frames: int  # usable frames
    skipped: int  # frames outside the luma range or of another size


def residual(gray: np.ndarray, size: int = 3) -> np.ndarray:
    """W = I - D(I), D a local Wiener filter with the noise level estimated as the median local variance."""
    mean = cv2.blur(gray, (size, size))
    var = np.maximum(cv2.blur(gray * gray, (size, size)) - mean * mean, 0.0)
    noise = float(np.median(var))
    gain = np.where(var > 0, np.maximum(var - noise, 0.0) / np.maximum(var, 1e-12), 0.0)
    return gray - (mean + gain * (gray - mean))


def _clean(k: np.ndarray) -> np.ndarray:
    k = k - k.mean(axis=1, keepdims=True)
    k = k - k.mean(axis=0, keepdims=True)
    h, w = k.shape
    for y in range(8):
        for x in range(8):
            k[y:h:8, x:w:8] -= k[y:h:8, x:w:8].mean()
    return k


def pce(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    corr = np.real(np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b))))
    peak = corr[0, 0]
    rolled = np.fft.fftshift(corr)
    cy, cx = rolled.shape[0] // 2, rolled.shape[1] // 2
    mask = np.ones_like(rolled, dtype=bool)
    mask[cy - PEAK_EXCLUDE : cy + PEAK_EXCLUDE + 1, cx - PEAK_EXCLUDE : cx + PEAK_EXCLUDE + 1] = False
    energy = float(np.mean(rolled[mask] ** 2))
    return float(np.sign(peak) * peak**2 / energy) if energy > 0 else 0.0


def fingerprint(frames: Iterable[np.ndarray]) -> Fingerprint | None:
    """frames: RGB uint8 fingerprint frames in capture order. None below MIN_FRAMES usable frames."""
    sums: list[list[np.ndarray]] = [[np.zeros(0), np.zeros(0)], [np.zeros(0), np.zeros(0)]]
    shape = None
    used = skipped = 0
    for img in frames:
        g = np.asarray(img)[..., 1].astype(np.float64)
        if not LUMA_RANGE[0] <= g.mean() <= LUMA_RANGE[1]:
            skipped += 1
            continue
        h, w = g.shape
        ch, cw = min(CROP, h), min(CROP, w)
        g = g[(h - ch) // 2 : (h - ch) // 2 + ch, (w - cw) // 2 : (w - cw) // 2 + cw] / 255.0
        if shape is None:
            shape = g.shape
            sums = [[np.zeros(shape), np.zeros(shape)], [np.zeros(shape), np.zeros(shape)]]
        if g.shape != shape:
            skipped += 1
            continue
        half = sums[used % 2]
        half[0] += residual(g) * g
        half[1] += g * g
        used += 1
    if used < MIN_FRAMES or shape is None:
        return None
    k = [_clean(num / np.maximum(den, 1e-12)) for num, den in sums]
    return Fingerprint(pce=pce(k[0], k[1]), frames=used, skipped=skipped)
