"""Command line: `python -m pulselens.cli analyze data/sessions/<id> [--plots] [--no-cache]`.

Reads a session bundle, finds faces (MediaPipe, cached in landmarks.jsonl), measures the regions, runs every
registered check and writes <bundle>/analysis/checks.json (+ analysis/plots/*.png with --plots).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pulselens import __version__
from pulselens.analyze import build_context, run_checks
from pulselens.calibration.thresholds import Thresholds
from pulselens.config import MODELS_DIR, load_config
from pulselens.store import (
    analysis_dir,
    iter_fingerprint_images,
    iter_frame_images,
    read_bundle,
    read_landmarks,
    write_json,
    write_landmarks,
)

FACE_MODEL = MODELS_DIR / "mediapipe" / "face_landmarker.task"


def _probe_with_fov(bundle) -> list[dict]:
    """probe.jsonl rows, each with `fov_scale` between the working frames nearest `before_t` and `after_t`."""
    import cv2

    from pulselens.vision.modes import fov_scale

    def frame_at(t):
        if not isinstance(t, int | float) or not bundle.frames:
            return None
        meta = min(bundle.frames, key=lambda f: abs(f["t"] - t))
        img = cv2.imread(str(bundle.path / "frames" / meta["file"]), cv2.IMREAD_COLOR)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if img is not None else None

    rows = []
    for row in bundle.probe:
        before, after = frame_at(row.get("before_t")), frame_at(row.get("after_t"))
        scale = fov_scale(before, after) if before is not None and after is not None else None
        rows.append({**row, "fov_scale": scale})
    return rows


def _landmarks(bundle, use_cache: bool) -> dict:
    cached = read_landmarks(bundle) if use_cache else None
    if cached is not None:
        print(f"Landmarks: cached ({sum(v is not None for v in cached.values())} of {len(cached)} frames with a face)")
        return cached
    if not FACE_MODEL.exists():
        print(f"Landmarks: {FACE_MODEL} is missing (run `make setup`); every face check will abstain.")
        return {f["i"]: None for f in bundle.frames}
    from pulselens.vision.face import Landmarker

    landmarker = Landmarker(FACE_MODEL)
    found: dict = {}
    try:
        for meta, image in iter_frame_images(bundle):
            found[meta["i"]] = landmarker.detect(image, meta["t"]) if image is not None else None
    finally:
        landmarker.close()
    write_landmarks(bundle, found)
    print(f"Landmarks: {sum(v is not None for v in found.values())} of {len(found)} frames with a face (cached)")
    return found


def analyze(path: Path, plots: bool, use_cache: bool) -> int:
    try:
        bundle = read_bundle(path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if bundle.skipped:
        print(f"Skipped {bundle.skipped} unreadable line(s) in frames.jsonl / pulses.jsonl")
    landmarks = _landmarks(bundle, use_cache)
    thresholds = Thresholds.bootstrap()
    quality = load_config()["quality"]
    from pulselens.vision.prnu import fingerprint

    ctx = build_context(
        ((meta, image, landmarks.get(meta["i"])) for meta, image in iter_frame_images(bundle)),
        bundle.pulses,
        thresholds=thresholds,
        profile=bundle.camera_details.get("profile_measured"),
        quality_min=float(quality["min"]),
        min_fps=float(quality["min_fps"]),
        details=bundle.camera_details,
        probe=_probe_with_fov(bundle),
        fingerprint=fingerprint(iter_fingerprint_images(bundle)),
    )
    results = run_checks(ctx)
    out = analysis_dir(bundle)
    write_json(
        out / "checks.json",
        {
            "session_id": bundle.session_id,
            "generated_by": f"pulselens {__version__} cli analyze",
            "frames": len(ctx.t),
            "pulses": len(bundle.pulses),
            "provisional_thresholds": thresholds.provisional,
            "checks": [r.model_dump() for r in results],
        },
    )

    print(f"\nSession {bundle.session_id}: {len(ctx.t)} frames, {len(ctx.colour_pulses)} colour pulses")
    if thresholds.provisional:
        print("PROVISIONAL THRESHOLDS: bootstrap values until set A calibration (M2.6)")
    for r in results:
        print(f"  {r.status.upper():8} {r.check_id:22} {r.reason}")

    if plots:
        _plots(ctx, out / "plots", thresholds)
        print(f"Plots: {out / 'plots'}")
    print(f"Results: {out / 'checks.json'}")
    return 0


def _plots(ctx, folder: Path, thresholds: Thresholds) -> None:
    import matplotlib.pyplot as plt

    from pulselens.plots import delay_figure, echo_figure

    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    params, source = thresholds.for_check("optical.light.delay")
    figs = {"light_delay.png": delay_figure(ctx, params["center_ms"], params["tolerance_ms"], source == "bootstrap")}
    for p in ctx.colour_pulses:
        figs[f"echo_{p.pulse_id}.png"] = echo_figure(ctx, p)
    for name, fig in figs.items():
        fig.savefig(folder / name)
        plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # Windows consoles may lack "±"; never crash on printing
    parser = argparse.ArgumentParser(prog="python -m pulselens.cli", description="PulseLens analysis tools")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="run every check on a session bundle")
    a.add_argument("bundle", type=Path, help="data/sessions/<id>")
    a.add_argument("--plots", action="store_true", help="write analysis/plots/*.png")
    a.add_argument("--no-cache", action="store_true", help="re-run face landmarks instead of using landmarks.jsonl")
    args = parser.parse_args(argv)
    if args.command == "analyze":
        return analyze(args.bundle, args.plots, not args.no_cache)
    return 2


if __name__ == "__main__":
    sys.exit(main())
