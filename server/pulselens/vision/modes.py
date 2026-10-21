"""Field of view across a camera mode switch (SPEC 7.3, 9.2 camera.modes). Pure: two frames in, a scale out.

ORB features on both frames, matched and fitted with a RANSAC similarity (cv2.estimateAffinePartial2D). Positions are
measured in units of each frame's width, so a frame that was only resized gives scale 1 and a sensor that changed its
crop gives the crop ratio. scale > 1: things look bigger after the switch (a narrower view).
"""

from __future__ import annotations

import cv2
import numpy as np

MIN_MATCHES = 12


def fov_scale(before: np.ndarray, after: np.ndarray) -> float | None:
    """RGB uint8 frames, any sizes. None when too few features match (a blank wall, a covered lens)."""
    orb = cv2.ORB_create(nfeatures=1500)
    pts = []
    for img in (before, after):
        grey = cv2.cvtColor(np.asarray(img, dtype=np.uint8), cv2.COLOR_RGB2GRAY)
        kp, des = orb.detectAndCompute(grey, None)
        if des is None or len(kp) < MIN_MATCHES:
            return None
        pts.append((np.array([k.pt for k in kp], dtype=np.float32) / grey.shape[1], des))
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(pts[0][1], pts[1][1])
    if len(matches) < MIN_MATCHES:
        return None
    src = np.array([pts[0][0][m.queryIdx] for m in matches])
    dst = np.array([pts[1][0][m.trainIdx] for m in matches])
    model, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=0.005)
    if model is None or inliers is None or int(inliers.sum()) < MIN_MATCHES:
        return None
    return float(np.hypot(model[0, 0], model[1, 0]))
