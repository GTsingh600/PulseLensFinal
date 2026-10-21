"""POST /analyze and GET /report (SPEC 6): the Lab's results after a recording, token-protected like events."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from tests.conftest import auth, create_session
from tests.fixtures.synth import light_session, write_bundle


def bundle_for(client, tmp_path: Path, **session) -> str:
    sid = create_session(client)["session_id"]
    src = write_bundle(tmp_path / "src", light_session(delay_ms=130, seed=21, **session))
    dst = client.app.state.hub.store.bundle_path(sid)
    for f in src.iterdir():
        if f.is_dir():
            shutil.copytree(f, dst / f.name, dirs_exist_ok=True)
        elif f.name != "meta.json":
            shutil.copy(f, dst / f.name)
    return sid


def wait_report(client, sid: str) -> dict:
    for _ in range(600):
        r = client.get(f"/api/sessions/{sid}/report", headers=auth(client, sid)).json()
        if r["status"] != "running":
            return r
        time.sleep(0.1)
    raise AssertionError("analysis never finished")


def test_a_recording_is_analysed_and_reported_with_its_qc(client, tmp_path) -> None:
    sid = bundle_for(client, tmp_path)
    assert client.get(f"/api/sessions/{sid}/report", headers=auth(client, sid)).json() == {"status": "none"}
    assert client.post(f"/api/sessions/{sid}/analyze", headers=auth(client, sid)).status_code == 202
    r = wait_report(client, sid)
    assert r["status"] == "done", r
    checks = {c["check_id"]: c for c in r["checks"]}
    assert checks["optical.light.delay"]["status"] == "pass"
    assert checks["optical.face_neck"]["status"] == "pass"
    assert {"camera.timing", "camera.fingerprint", "camera.noise_curve"} <= set(checks)
    assert r["provisional_thresholds"] is True
    assert r["qc"]["face_visible"] == 1.0 and r["qc"]["fps"] > 25


def test_the_report_flags_a_late_face(client, tmp_path) -> None:
    sid = bundle_for(client, tmp_path, face_lag_ms=100)
    client.post(f"/api/sessions/{sid}/analyze", headers=auth(client, sid))
    checks = {c["check_id"]: c["status"] for c in wait_report(client, sid)["checks"]}
    assert checks["optical.face_neck"] == "fail"


def test_results_need_the_session_token(client, tmp_path) -> None:
    sid = bundle_for(client, tmp_path)
    assert client.post(f"/api/sessions/{sid}/analyze").status_code == 401
    assert client.get(f"/api/sessions/{sid}/report").status_code == 401
    assert client.get(f"/api/sessions/{sid}/report", headers={"X-Session-Token": "guess"}).status_code == 401


def test_an_empty_bundle_reports_an_error_not_a_crash(client) -> None:
    sid = create_session(client)["session_id"]  # nothing recorded: no frames.jsonl
    assert client.post(f"/api/sessions/{sid}/analyze", headers=auth(client, sid)).status_code == 202
    r = wait_report(client, sid)
    assert r["status"] == "error" and "frames.jsonl" in r["error"]
    assert client.get("/api/health").status_code == 200
