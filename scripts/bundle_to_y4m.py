"""Turn a recorded session bundle into a .y4m file for Chromium's fake camera (local replay test only).

    python scripts/bundle_to_y4m.py data/sessions/<id> [data/local/replay.y4m]

The replay e2e project (`npx playwright test --project=brave-replay`) plays this file as the camera, so the Lab
Record flow runs against a video that cannot answer the new session's flashes: the judge-replay scenario without a
phone. The output holds a real face, so it stays under data/ (gitignored) and is never a committed fixture
(CLAUDE.md test rules); use only sessions whose person consented.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import cv2


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bundle = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else Path("data/local/replay.y4m")
    frames = sorted(
        (json.loads(x) for x in (bundle / "frames.jsonl").read_text().splitlines() if x.strip()), key=lambda f: f["i"]
    )
    if len(frames) < 2:
        print(f"error: {bundle} has fewer than 2 frames", file=sys.stderr)
        return 2
    interval = statistics.median(b["t"] - a["t"] for a, b in zip(frames, frames[1:], strict=False))
    fps = max(1, round(1000 / interval))
    w, h = frames[0]["w"] // 2 * 2, frames[0]["h"] // 2 * 2
    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with out.open("wb") as f:
        f.write(f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A1:1 C420jpeg\n".encode())
        for meta in frames:
            img = cv2.imread(str(bundle / "frames" / meta["file"]), cv2.IMREAD_COLOR)
            if img is None:
                continue
            img = cv2.resize(img, (w, h)) if img.shape[:2] != (h, w) else img
            f.write(b"FRAME\n")
            f.write(cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420).tobytes())
            written += 1
    print(f"{out}: {written} frames, {w}x{h} at {fps} fps")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
