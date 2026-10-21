"""Multi-vector integration (no browser): synthetic bundles on disk → `cli analyze` → checks.json.

Each vector is a session condition or a damaged bundle. The pipeline must never crash, and each check must land
on an allowed status. Attack-like vectors are the effects a detector looks for (no echo, a late face), produced by
the light model in fixtures/synth.py, not by any attack tool.
"""

import json
import random
from collections.abc import Callable
from pathlib import Path

import pytest

from pulselens import cli
from tests.fixtures.synth import light_session, write_bundle

LIGHT, FACE_NECK = "optical.light.delay", "optical.face_neck"
PASS, FAIL, ABSTAIN = {"pass"}, {"fail"}, {"abstain"}


def checks(bundle: Path) -> dict[str, str]:
    data = json.loads((bundle / "analysis" / "checks.json").read_text())
    return {c["check_id"]: c["status"] for c in data["checks"]}


def rewrite_jsonl(path: Path, edit: Callable[[list[str]], list[str]]) -> None:
    path.write_text("".join(line + "\n" for line in edit(path.read_text().splitlines())))


def corrupt_jpegs(bundle: Path, every: int) -> None:
    for k, f in enumerate(sorted((bundle / "frames").iterdir())):
        if k % every == 0:
            f.write_bytes(b"\xff\xd8 not a jpeg")


def delete_jpegs(bundle: Path, every: int) -> None:
    for k, f in enumerate(sorted((bundle / "frames").iterdir())):
        if k % every == 0:
            f.unlink()


def late_acks(bundle: Path) -> None:
    def edit(lines: list[str]) -> list[str]:
        return [json.dumps({**json.loads(x), "ok": False, "error": "late"}) for x in lines]

    rewrite_jsonl(bundle / "pulses.jsonl", edit)


def shuffle_frame_lines(bundle: Path) -> None:
    rewrite_jsonl(bundle / "frames.jsonl", lambda lines: random.Random(0).sample(lines, len(lines)))


def duplicate_frame_lines(bundle: Path) -> None:
    rewrite_jsonl(bundle / "frames.jsonl", lambda lines: lines + lines[100:130])  # a batch uploaded twice


VECTORS: dict[str, tuple[dict, Callable[[Path], None] | None, dict[str, set[str]]]] = {
    # name: (light_session args + bundle args, damage, allowed statuses per check)
    "genuine": ({}, None, {LIGHT: PASS, FACE_NECK: PASS}),
    "face_redrawn_100ms_late": ({"face_lag_ms": 100}, None, {FACE_NECK: FAIL}),
    "neck_answers_face_does_not": ({"face_echo": False}, None, {LIGHT: FAIL, FACE_NECK: FAIL}),
    "nothing_answers_the_flash": ({"face_echo": False, "neck_echo": False}, None, {LIGHT: FAIL}),
    "no_face_in_frames": ({"face_in_frames": False}, None, {LIGHT: ABSTAIN, FACE_NECK: ABSTAIN}),
    "neck_out_of_frame": ({"chin_y": 236.0}, None, {LIGHT: PASS, FACE_NECK: ABSTAIN}),
    "frame_lines_shuffled": ({}, shuffle_frame_lines, {LIGHT: PASS, FACE_NECK: PASS}),
    "a_batch_uploaded_twice": ({}, duplicate_frame_lines, {LIGHT: PASS, FACE_NECK: PASS}),
    "every_7th_jpeg_corrupt": ({}, lambda b: corrupt_jpegs(b, 7), {LIGHT: PASS, FACE_NECK: PASS}),
    "every_3rd_jpeg_missing": ({}, lambda b: delete_jpegs(b, 3), {LIGHT: PASS | ABSTAIN, FACE_NECK: PASS | ABSTAIN}),
    "pulse_log_missing": ({}, lambda b: (b / "pulses.jsonl").unlink(), {LIGHT: ABSTAIN, FACE_NECK: ABSTAIN}),
    "every_ack_late": ({}, late_acks, {LIGHT: ABSTAIN, FACE_NECK: ABSTAIN}),
    "low_fps_genuine": ({"fps": 15.0}, None, {LIGHT: PASS, FACE_NECK: PASS | ABSTAIN}),
}


@pytest.mark.parametrize("name", list(VECTORS))
def test_cli_vector(tmp_path: Path, name: str) -> None:
    args, damage, allowed = VECTORS[name]
    bundle_args = {k: args.pop(k) for k in ("chin_y", "face_in_frames") if k in args}
    bundle = write_bundle(tmp_path, light_session(delay_ms=130, seed=11, **args), **bundle_args)
    if damage:
        damage(bundle)
    assert cli.main(["analyze", str(bundle)]) == 0
    got = checks(bundle)
    for check_id, statuses in allowed.items():
        assert got[check_id] in statuses, (name, check_id, got)


@pytest.mark.parametrize(
    ("file", "bad_line"),
    [("frames.jsonl", "{not json"), ("pulses.jsonl", "{not json"), ("frames.jsonl", '{"t": 5.0}')],
)
def test_a_damaged_log_line_is_skipped_and_reported(tmp_path: Path, file: str, bad_line: str, capsys) -> None:
    bundle = write_bundle(tmp_path, light_session(seed=12))
    rewrite_jsonl(bundle / file, lambda lines: lines[:50] + [bad_line] + lines[50:])
    assert cli.main(["analyze", str(bundle)]) == 0
    assert "Skipped 1 unreadable line" in capsys.readouterr().out
    assert checks(bundle)[LIGHT] == "pass"  # one lost line does not lose the session
