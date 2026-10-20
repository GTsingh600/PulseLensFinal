"""Face regions per frame (SPEC 9.1).

`regions_from_landmarks` is pure geometry on MediaPipe FaceLandmarker landmark positions (pixels):
- skin: forehead + left and right cheek, boxes placed between the landmarks so eyes, brows and lips stay out
- left/right cheek: by image side (image left = the person's right in an unmirrored camera frame)
- neck: a box below the chin, 0.6 face widths wide, 0.05 to 0.45 face heights below the chin, clipped to the frame
- background: the frame minus the face box dilated 1.6x and minus a bottom-centre body block

`Landmarker` wraps the MediaPipe model (VIDEO mode) and returns only the landmarks the geometry uses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# MediaPipe face-mesh indices
FOREHEAD_TOP, CHIN, SIDE_A, SIDE_B = 10, 152, 234, 454
BROWS = (70, 63, 105, 66, 107, 336, 296, 334, 293, 300)
BROW_INNER_A, BROW_INNER_B = 105, 334
LOWER_LIDS = (145, 374)
CHEEKS = (50, 280)
LIPS = (13, 14)
LANDMARKS_USED: tuple[int, ...] = tuple(
    sorted({FOREHEAD_TOP, CHIN, SIDE_A, SIDE_B, *BROWS, *LOWER_LIDS, *CHEEKS, *LIPS})
)

NECK_WIDTH = 0.6  # face widths
NECK_TOP, NECK_BOTTOM = 0.05, 0.45  # face heights below the chin
BACKGROUND_DILATE = 1.6
BODY_HALF_WIDTH = 1.25  # face widths either side of the face centre, from the chin down
CHEEK_SIZE = 0.18  # face widths


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def clip(self, w: int, h: int) -> Box:
        return Box(min(max(self.x0, 0), w), min(max(self.y0, 0), h), min(max(self.x1, 0), w), min(max(self.y1, 0), h))

    def scaled(self, f: float) -> Box:
        cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        hw, hh = (self.x1 - self.x0) * f / 2, (self.y1 - self.y0) * f / 2
        return Box(cx - hw, cy - hh, cx + hw, cy + hh)

    def slices(self) -> tuple[slice, slice]:
        """Integer pixel slices (rows, cols) of this box."""
        return slice(round(self.y0), round(self.y1)), slice(round(self.x0), round(self.x1))


@dataclass(frozen=True)
class FaceRegions:
    face_box: Box
    forehead: Box
    cheek_left: Box
    cheek_right: Box
    neck: Box
    neck_coverage: float
    background_exclude: tuple[Box, ...]

    @property
    def skin(self) -> tuple[Box, ...]:
        return (self.forehead, self.cheek_left, self.cheek_right)


def regions_from_landmarks(lm: Mapping[int, tuple[float, float]], w: int, h: int) -> FaceRegions:
    """Regions from pixel landmark positions (at least LANDMARKS_USED)."""
    xs = [p[0] for p in lm.values()]
    ys = [p[1] for p in lm.values()]
    face = Box(min(xs), min(ys), max(xs), max(ys))
    fw = abs(lm[SIDE_B][0] - lm[SIDE_A][0]) or (face.x1 - face.x0)
    fh = abs(lm[CHIN][1] - lm[FOREHEAD_TOP][1]) or (face.y1 - face.y0)
    chin_x, chin_y = lm[CHIN]

    brow_top = min(lm[i][1] for i in BROWS)
    top = lm[FOREHEAD_TOP][1]
    band = max(brow_top - top, 1.0)
    fx = sorted((lm[BROW_INNER_A][0], lm[BROW_INNER_B][0]))
    forehead = Box(fx[0], top + 0.2 * band, fx[1], brow_top - 0.2 * band)

    lid_y = max(lm[i][1] for i in LOWER_LIDS)
    lip_y = min(lm[i][1] for i in LIPS)
    half = CHEEK_SIZE * fw / 2
    cheeks = []
    for i in CHEEKS:
        cx, cy = lm[i]
        y0 = max(cy - half, lid_y + 0.1 * (lip_y - lid_y))
        y1 = min(cy + half, lip_y - 0.1 * (lip_y - lid_y))
        cheeks.append(Box(cx - half, y0, cx + half, y1))
    cheek_left, cheek_right = sorted(cheeks, key=lambda b: b.x0)

    nominal_neck = Box(
        chin_x - NECK_WIDTH * fw / 2, chin_y + NECK_TOP * fh, chin_x + NECK_WIDTH * fw / 2, chin_y + NECK_BOTTOM * fh
    )
    neck = nominal_neck.clip(w, h)
    coverage = neck.area / nominal_neck.area if nominal_neck.area else 0.0

    centre_x = (face.x0 + face.x1) / 2
    body = Box(centre_x - BODY_HALF_WIDTH * fw, chin_y, centre_x + BODY_HALF_WIDTH * fw, h)
    return FaceRegions(
        face_box=face,
        forehead=forehead.clip(w, h),
        cheek_left=cheek_left.clip(w, h),
        cheek_right=cheek_right.clip(w, h),
        neck=neck,
        neck_coverage=coverage,
        background_exclude=(face.scaled(BACKGROUND_DILATE), body),
    )


def to_pixels(
    lm_norm: Mapping[int, tuple[float, float]] | Mapping[str, list[float]], w: int, h: int
) -> dict[int, tuple[float, float]]:
    """Normalised landmarks (MediaPipe output or the landmarks.jsonl cache) to pixels."""
    return {int(k): (float(v[0]) * w, float(v[1]) * h) for k, v in lm_norm.items()}


class Landmarker:
    """MediaPipe FaceLandmarker in VIDEO mode, one face. Returns normalised positions of LANDMARKS_USED."""

    def __init__(self, model_path: Path) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, rgb: np.ndarray, t_ms: float) -> dict[int, tuple[float, float]] | None:
        ts = max(int(round(t_ms)), self._last_ts + 1)  # MediaPipe needs strictly increasing timestamps
        self._last_ts = ts
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, ts)
        if not result.face_landmarks:
            return None
        pts = result.face_landmarks[0]
        return {i: (pts[i].x, pts[i].y) for i in LANDMARKS_USED}

    def close(self) -> None:
        self._landmarker.close()
