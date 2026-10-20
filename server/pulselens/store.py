"""Session bundle files (SPEC 4.1). With cli.py and api/, the only place that touches the disk (CLAUDE.md).

Track A/B part: reading bundles for analysis and writing analysis outputs. Track C adds the session store
(SQLite + writing bundles) for M1.2 in this module.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class Bundle:
    path: Path
    meta: dict[str, Any]
    frames: list[dict[str, Any]]  # frames.jsonl, sorted by frame index
    pulses: list[dict[str, Any]]  # pulses.jsonl

    @property
    def session_id(self) -> str:
        return str(self.meta.get("session_id") or self.path.name)

    @property
    def camera_details(self) -> dict[str, Any]:
        return self.meta.get("camera_details") or {}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_bundle(path: Path) -> Bundle:
    if not (path / "frames.jsonl").exists():
        raise FileNotFoundError(f"{path} is not a session bundle (no frames.jsonl)")
    meta_file = path / "meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    frames = sorted(_jsonl(path / "frames.jsonl"), key=lambda f: f["i"])
    return Bundle(path=path, meta=meta, frames=frames, pulses=_jsonl(path / "pulses.jsonl"))


def iter_frame_images(bundle: Bundle) -> Iterator[tuple[dict[str, Any], np.ndarray | None]]:
    """(frames.jsonl line, RGB uint8 image or None when the file is missing or unreadable)."""
    for meta in bundle.frames:
        img = cv2.imread(str(bundle.path / "frames" / meta["file"]), cv2.IMREAD_COLOR)
        yield meta, (cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img is not None else None)


LANDMARKS_CACHE = "landmarks.jsonl"


def read_landmarks(bundle: Bundle) -> dict[int, dict[str, list[float]] | None] | None:
    """Cached landmarks by frame index, or None when the cache is missing or doesn't cover every frame."""
    rows = _jsonl(bundle.path / LANDMARKS_CACHE)
    cache = {int(r["i"]): r.get("landmarks") for r in rows}
    return cache if all(f["i"] in cache for f in bundle.frames) else None


def write_landmarks(bundle: Bundle, landmarks: dict[int, dict[int, tuple[float, float]] | None]) -> None:
    lines = [
        json.dumps(
            {
                "i": i,
                "landmarks": None if lm is None else {str(k): [round(x, 6), round(y, 6)] for k, (x, y) in lm.items()},
            }
        )
        for i, lm in sorted(landmarks.items())
    ]
    (bundle.path / LANDMARKS_CACHE).write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def analysis_dir(bundle: Bundle) -> Path:
    out = bundle.path / "analysis"
    out.mkdir(exist_ok=True)
    return out


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
