"""Session bundle files (SPEC 4.1). With cli.py and api/, the only place that touches the disk (CLAUDE.md).

- Reading bundles for analysis and writing analysis outputs (cli analyze).
- SessionStore: the live server's sessions, indexed in SQLite, each written as a bundle as data arrives (M1.2).
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing
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


# --- Live sessions (M1.2) --------------------------------------------------------------------------------------------

FRAME_NAME = re.compile(r"^\d{6}\.jpg$")
JSONL_FILES = frozenset({"frames.jsonl", "probe.jsonl", "pulses.jsonl", "sensors.jsonl"})
FRAME_FOLDERS = frozenset({"frames", "fp"})


class SessionStore:
    """sessions/<id>/ bundles under `root`, indexed in root/pulselens.sqlite (id, created, mode, product, status)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "sessions").mkdir(parents=True, exist_ok=True)
        self._db = root / "pulselens.sqlite"
        with closing(sqlite3.connect(self._db)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created_ms REAL, mode TEXT, product TEXT, "
                "scenario TEXT, label TEXT, status TEXT, finalized_ms REAL)"
            )

    def bundle_path(self, session_id: str) -> Path:
        return self.root / "sessions" / session_id

    def exists(self, session_id: str) -> bool:
        if not re.fullmatch(r"[0-9a-f]{16}", session_id):
            return False
        with closing(sqlite3.connect(self._db)) as db:
            return db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None

    def create(self, mode: str, product: str, scenario: str | None, label: dict[str, Any] | None) -> str:
        session_id = secrets.token_hex(8)
        bundle = self.bundle_path(session_id)
        for folder in FRAME_FOLDERS:
            (bundle / folder).mkdir(parents=True)
        created = time.time() * 1000
        meta = {"session_id": session_id, "created_ms": created, "mode": mode, "scenario": scenario, "product": product,
                "label": label, "camera_details": {}, "profiles": None, "plan": None}
        write_json(bundle / "meta.json", meta)
        with closing(sqlite3.connect(self._db)) as db, db:
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, 'open', NULL)",
                (session_id, created, mode, product, scenario, json.dumps(label) if label else None),
            )
        return session_id

    def meta(self, session_id: str) -> dict[str, Any]:
        return json.loads((self.bundle_path(session_id) / "meta.json").read_text(encoding="utf-8"))

    def update_meta(self, session_id: str, **patch: Any) -> dict[str, Any]:
        meta = {**self.meta(session_id), **patch}
        write_json(self.bundle_path(session_id) / "meta.json", meta)
        return meta

    def merge_details(self, session_id: str, partial: dict[str, Any]) -> dict[str, Any]:
        """CameraDetails arrive in parts (SPEC 7.1 step 4); later values win."""
        meta = self.meta(session_id)
        return self.update_meta(session_id, camera_details={**(meta.get("camera_details") or {}), **partial})

    def append_jsonl(self, session_id: str, name: str, rows: list[dict[str, Any]]) -> None:
        if name not in JSONL_FILES:
            raise ValueError(f"not a bundle log: {name}")
        with open(self.bundle_path(session_id) / name, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)

    def save_frame(self, session_id: str, folder: str, name: str, data: bytes) -> None:
        if folder not in FRAME_FOLDERS or not FRAME_NAME.match(name):
            raise ValueError(f"bad frame file {folder}/{name}")
        (self.bundle_path(session_id) / folder / name).write_bytes(data)

    def finalize(self, session_id: str, summary: dict[str, Any]) -> None:
        now = time.time() * 1000
        self.update_meta(session_id, finalize=summary, finalized_ms=now)
        with closing(sqlite3.connect(self._db)) as db, db:
            db.execute("UPDATE sessions SET status = 'finalized', finalized_ms = ? WHERE id = ?", (now, session_id))
