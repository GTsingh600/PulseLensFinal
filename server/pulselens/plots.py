"""Analysis plots for `cli analyze --plots` (matplotlib figures; the CLI saves them)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from pulselens.checks.base import AnalysisContext, Pulse  # noqa: E402
from pulselens.checks.echo import NO_ECHO_MS, EchoOnset, echo_onset  # noqa: E402

FACE, NECK = "#d95f02", "#1b9e77"


def echo_figure(ctx: AnalysisContext, pulse: Pulse, title_note: str = "") -> Figure:
    """Face and neck projection on the pulse colour around one flash, with thresholds and onsets."""
    a_min = float(ctx.thresholds.echo["a_min"])
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=110)
    duration = (pulse.ended or 0) - (pulse.painted or 0)
    ax.axvspan(0, duration, color=tuple(np.clip(_srgb(pulse.colour), 0, 1)), alpha=0.25, label="flash")
    for region, colour in (("skin", FACE), ("neck", NECK)):
        series = ctx.regions.get(region)
        if series is None:
            continue
        o: EchoOnset = echo_onset(ctx.t, series, pulse, region=region, a_min=a_min)
        name = "face" if region == "skin" else "neck"
        if not o.valid:
            ax.plot([], [], color=colour, label=f"{name}: not measurable ({o.reason})")
            continue
        ax.plot(
            o.t_rel,
            o.p,
            "-o",
            ms=3,
            color=colour,
            label=f"{name}" + (f": onset {o.onset_ms:.0f} ms" if o.onset_ms is not None else ": no echo"),
        )
        ax.axhline(o.threshold, color=colour, ls=":", lw=1)
        if o.onset_ms is not None:
            ax.axvline(o.onset_ms, color=colour, ls="--", lw=1)
    ax.set_xlabel("ms after the flash was painted")
    ax.set_ylabel("colour change towards the flash")
    ax.set_title(f"Echo, pulse {pulse.pulse_id} {title_note}".strip(), fontsize=10)
    ax.legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    return fig


def delay_figure(ctx: AnalysisContext, center: float, tolerance: float, provisional: bool) -> Figure:
    """Face echo delay per colour pulse against the (provisional) band."""
    a_min = float(ctx.thresholds.echo["a_min"])
    skin = ctx.regions.get("skin")
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=110)
    ax.axhspan(
        center - tolerance,
        center + tolerance,
        color="#999",
        alpha=0.2,
        label="PROVISIONAL band" if provisional else "genuine band",
    )
    for k, p in enumerate(ctx.colour_pulses):
        if skin is None:
            break
        o = echo_onset(ctx.t, skin, p, region="skin", a_min=a_min)
        if not o.valid:
            ax.plot(k, 0, "x", color="#888")
        elif o.onset_ms is None:
            ax.plot(k, NO_ECHO_MS, "v", color="#c00", label="no echo (counted as 1000 ms)" if k == 0 else None)
        else:
            ax.plot(k, o.onset_ms, "o", color=FACE)
    ax.set_xlabel("colour pulse")
    ax.set_ylabel("face echo delay, ms")
    ax.set_title("Light echo timing (x = not measurable)", fontsize=10)
    ax.legend(fontsize=7)
    fig.tight_layout()
    return fig


def _srgb(linear: np.ndarray | None) -> np.ndarray:
    if linear is None:
        return np.array([0.8, 0.8, 0.8])
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(linear, 1 / 2.4) - 0.055)
