"""Synthetic test fixtures (CLAUDE.md: no network and no real faces in tests). Every track adds generators here.

Light-suite model (track B, M1.5): each region reflects ambient light plus the screen,
`rgb(t) = albedo * (ambient + k * screen(t - delay))`, where the screen is the neutral grey between pulses and the
pulse colour while it is painted. A frame's value is the average over its exposure, the frame interval before its
time `t`, so an echo onset falls between frames as it does on a real sensor. Region means get Gaussian noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from pulselens.checks.base import Pulse, RegionSeries
from pulselens.vision.linearize import linear_to_srgb, srgb_to_linear

# What packages/capture paints (sRGB 0-255) at Y = 0.5: hue -> colour, and the neutral grey between pulses.
ISO_SRGB = {
    0: (250, 163, 185),
    60: (222, 183, 81),
    120: (142, 205, 87),
    180: (58, 209, 190),
    240: (142, 192, 246),
    300: (222, 168, 244),
}
NEUTRAL_SRGB = (188, 188, 188)

SKIN = np.array([0.42, 0.27, 0.20])  # linear albedo-ish values; only ratios matter
SHIRT = np.array([0.30, 0.32, 0.38])
WALL = np.array([0.35, 0.35, 0.33])


@dataclass
class LightSession:
    t: np.ndarray
    regions: dict[str, RegionSeries]
    pulses: list[dict]  # pulses.jsonl lines
    truth: dict = field(default_factory=dict)

    @property
    def pulse_objs(self) -> list[Pulse]:
        return [Pulse.from_log(p) for p in self.pulses]


def _pulse_log(start_ms: float, n_colour: int, n_split: int, n_white: int, duration: float, gap: float) -> list[dict]:
    hues = [0, 60, 120, 180, 240, 300][:n_colour]
    plan: list[dict] = [{"mode": "colour", "hue_deg": h} for h in hues]
    plan += [
        {
            "mode": "split",
            "left_hue_deg": hues[2 * k % len(hues)],
            "right_hue_deg": (hues[2 * k % len(hues)] + 180) % 360,
        }
        for k in range(n_split)
    ]
    plan += [{"mode": "white"} for _ in range(n_white)]
    out, t = [], start_ms
    for k, params in enumerate(plan):
        neutral = list(NEUTRAL_SRGB)
        if params["mode"] == "colour":
            shown = {"neutral": neutral, "rgb": list(ISO_SRGB[params["hue_deg"]])}
        elif params["mode"] == "split":
            shown = {
                "neutral": neutral,
                "left": list(ISO_SRGB[params["left_hue_deg"]]),
                "right": list(ISO_SRGB[params["right_hue_deg"]]),
            }
        else:
            shown = {"neutral": neutral, "rgb": [255, 255, 255]}
        out.append(
            {
                "pulse_id": f"L{k}",
                "kind": "light",
                "source": "orchestrator",
                "params": {**params, "duration_ms": duration},
                "received": t - 20,
                "applied": t - 15,
                "painted": t,
                "ended": t + duration,
                "ok": True,
                "sig": "x",
                "shown": shown,
                "error": None,
            }
        )
        t += duration + gap
    return out


def _screen(pulses: list[dict], side: str) -> list[tuple[float, float, np.ndarray]]:
    """(start, end, linear colour) intervals of the screen light reaching one side of the face."""
    out = []
    for p in pulses:
        s = p["shown"]
        rgb = s["rgb"] if "rgb" in s else s[side]
        out.append((p["painted"], p["ended"], srgb_to_linear(np.array(rgb, float) / 255)))
    return out


def _render(t: np.ndarray, exposure: float, intervals, delay: float, albedo, ambient: float, k: float) -> np.ndarray:
    """Exposure-averaged region colour: albedo * (ambient + k * screen)."""
    neutral = srgb_to_linear(np.array(NEUTRAL_SRGB, float) / 255)
    light = np.tile(ambient + k * neutral, (len(t), 1))
    for start, end, colour in intervals:
        a, b = start + delay, end + delay
        overlap = np.clip(np.minimum(t, b) - np.maximum(t - exposure, a), 0, None) / exposure
        light += overlap[:, None] * k * (colour - neutral)
    return albedo * light


def light_session(
    *,
    fps: float = 30.0,
    delay_ms: float = 120.0,
    face_lag_ms: float = 0.0,
    face_echo: bool = True,
    neck_echo: bool = True,
    neck_coverage: float = 1.0,
    neck_gain: float = 1.0,
    neck_lead_ms: float = 0.0,
    face_present: bool = True,
    n_colour: int = 6,
    n_split: int = 2,
    n_white: int = 2,
    noise: float = 0.0006,
    jitter_ms: float = 1.0,
    k: float = 0.35,
    ambient: float = 0.5,
    duration_ms: float = 400.0,
    gap_ms: float = 1000.0,
    seed: int = 0,
) -> LightSession:
    """Region means and a pulse log for one light suite. Echo `delay_ms` after `painted`; the face can lag.

    `neck_gain` scales how strongly the neck (or shirt) answers the screen, as a darker or shinier shirt does.
    `neck_lead_ms` models a rolling shutter: the neck rows are read after the face rows, so in frame times the
    neck's echo shows up that much earlier than the face's, with no face-swap involved.
    """
    rng = np.random.default_rng(seed)
    pulses = _pulse_log(1000.0, n_colour, n_split, n_white, duration_ms, gap_ms)
    end = pulses[-1]["ended"] + 1500
    interval = 1000.0 / fps
    base = np.arange(0, end, interval)
    t = np.sort(base + rng.normal(0, jitter_ms, len(base)))
    regions = {}
    face_k = k if face_echo else 0.0
    for name, albedo, kk, lag, side in [
        ("skin", SKIN, face_k, face_lag_ms, "left"),
        ("cheek_left", SKIN, face_k, face_lag_ms, "left"),
        ("cheek_right", SKIN, face_k, face_lag_ms, "right"),
        ("neck", SHIRT, k * neck_gain if neck_echo else 0.0, -neck_lead_ms, "left"),
        ("background", WALL, 0.05 * k, 0.0, "left"),
    ]:
        rgb = _render(t, interval, _screen(pulses, side), delay_ms + lag, albedo, ambient, kk)
        rgb = rgb + rng.normal(0, noise, rgb.shape)
        cov = np.full(len(t), 1.0)
        if name != "background" and not face_present:
            cov[:] = 0.0
        if name == "neck":
            cov[:] = neck_coverage if face_present else 0.0
        regions[name] = RegionSeries(rgb=rgb, coverage=cov)
    truth = {"delay_ms": delay_ms, "face_lag_ms": face_lag_ms, "frame_ms": interval}
    return LightSession(t=t, regions=regions, pulses=pulses, truth=truth)


# --- Synthetic bundle on disk (SPEC 4.1) with a landmarks cache, for the CLI ---------------------------------------

W, H = 320, 240


def synthetic_landmarks(chin_y: float = 150.0) -> dict[int, tuple[float, float]]:
    """Pixel landmarks of a frontal face box 80 wide, 110 tall, chin at `chin_y`, centred at x = 160."""
    top = chin_y - 110
    cx, mid = 160.0, chin_y - 55
    return {
        10: (cx, top),
        152: (cx, chin_y),
        234: (120, mid),
        454: (200, mid),
        70: (128, top + 25),
        105: (140, top + 22),
        66: (146, top + 21),
        107: (152, top + 22),
        63: (134, top + 23),
        300: (192, top + 25),
        334: (180, top + 22),
        296: (174, top + 21),
        336: (168, top + 22),
        293: (186, top + 23),
        145: (140, top + 44),
        374: (180, top + 44),
        50: (138, top + 66),
        280: (182, top + 66),
        13: (cx, top + 88),
        14: (cx, top + 92),
    }


def write_bundle(root: Path, session: LightSession, *, chin_y: float = 150.0, face_in_frames: bool = True) -> Path:
    """Draws frames whose face, neck and wall boxes carry the session's region colours, plus a landmarks cache."""
    bundle = root / "synth-session"
    (bundle / "frames").mkdir(parents=True, exist_ok=True)
    lm = synthetic_landmarks(chin_y)
    face = (120, int(chin_y - 110), 200, int(chin_y))
    neck = (130, int(chin_y), 190, H)
    frames, landmarks = [], []
    for i, t in enumerate(session.t):
        img = np.empty((H, W, 3))
        img[:] = session.regions["background"].rgb[i]
        if face_in_frames:
            img[neck[1] : neck[3], neck[0] : neck[2]] = session.regions["neck"].rgb[i]
            img[face[1] : face[3], face[0] : face[2]] = session.regions["skin"].rgb[i]
            img[face[1] : face[3], 160 : face[2]] = session.regions["cheek_right"].rgb[i]
        srgb = np.clip(np.round(linear_to_srgb(np.clip(img, 0, 1)) * 255), 0, 255).astype(np.uint8)
        name = f"{i:06d}.jpg"
        cv2.imwrite(
            str(bundle / "frames" / name), cv2.cvtColor(srgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95]
        )
        frames.append(
            {
                "i": i,
                "t": float(t),
                "capture_time": float(t),
                "presented_frames": i,
                "w": W,
                "h": H,
                "file": name,
                "fp_file": None,
            }
        )
        landmarks.append(
            {"i": i, "landmarks": {str(k): [x / W, y / H] for k, (x, y) in lm.items()} if face_in_frames else None}
        )
    (bundle / "frames.jsonl").write_text("".join(json.dumps(f) + "\n" for f in frames))
    (bundle / "pulses.jsonl").write_text("".join(json.dumps(p) + "\n" for p in session.pulses))
    (bundle / "landmarks.jsonl").write_text("".join(json.dumps(x) + "\n" for x in landmarks))
    (bundle / "meta.json").write_text(
        json.dumps(
            {
                "session_id": "synth-session",
                "mode": "superset",
                "product": "lab",
                "label": None,
                "camera_details": {"channel": "desktop_browser", "profile_measured": "desktop_browser|ge27"},
                "source": "tests/fixtures/synth.py",
            }
        )
    )
    return bundle
