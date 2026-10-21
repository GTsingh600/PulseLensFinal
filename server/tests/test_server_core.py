"""M1.2 acceptance (pytest) plus the REST and WebSocket contract the capture device relies on (SPEC 5, 6)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from pulselens.hub import CUSTOMER_FORBIDDEN_KEYS, CustomerPayloadError, assert_customer_safe
from pulselens.pulses import sign_pulse
from tests.conftest import PASSCODE, SECRET, auth, create_session, default_ack, get_events, run_capture


def bundle_dir(client, sid: str) -> Path:
    return client.app.state.hub.store.bundle_path(sid)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --- events: strictly increasing seq, catch-up returns exactly the missed events -------------------------------------


def test_events_have_strictly_increasing_seq_and_are_saved(client) -> None:
    s = create_session(client)
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws)
    events = get_events(client, s["session_id"])
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(seqs))) and len(seqs) > 10
    assert events[0]["type"] == "session.created"
    assert jsonl(bundle_dir(client, s["session_id"]) / "events.jsonl") == events
    types = [e["type"] for e in events]
    assert types.count("pulse.released") == 10 and types.count("pulse.acked") == 10
    assert [e["payload"]["stage"] for e in events if e["type"] == "stage.changed"] == ["camera", "coach", "pulses"]


def test_catch_up_returns_exactly_the_missed_events(client) -> None:
    s = create_session(client)
    sid = s["session_id"]
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws)
    everything = get_events(client, sid)
    for seen_up_to in (0, 7, len(everything) - 2):
        missed = get_events(client, sid, seen_up_to + 1)
        assert missed == everything[seen_up_to + 1 :]
    assert get_events(client, sid, len(everything)) == []


def test_a_presenter_reconnecting_with_from_gets_the_missed_events_first(client) -> None:
    s = create_session(client)
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws)
    everything = get_events(client, s["session_id"])
    with client.websocket_connect(f"{s['ws_url']}?role=presenter&from=5&token={s['token']}") as viewer:
        got = [viewer.receive_json() for _ in range(len(everything) - 5)]
    assert [m["type"] for m in got] == ["event"] * len(got)
    assert [m["event"] for m in got] == everything[5:]


# --- customer payloads never contain scores, check names or families ------------------------------------------------


def _keys(obj, out: set[str]) -> set[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def test_customer_role_messages_never_contain_score_check_id_or_family(client) -> None:
    s = create_session(client, mode="live", product="demo")
    sid = s["session_id"]
    runtime = client.app.state.hub.runtime(sid)
    secret_result = {
        "check_id": "optical.face_neck",
        "family": "optical",
        "score": 4.2,
        "status": "fail",
        "reason": "The face lagged the neck by 120 ms on 7 of 8 pulses.",
    }

    def leak_attempt(_pulse: dict) -> None:
        # Results land on the bus while the customer is mid-session; none may reach the customer.
        client.portal.call(runtime.bus.emit, "check.result", secret_result)
        client.portal.call(runtime.bus.emit, "coverage.update", {"liveswap": ["optical"]})

    joined = client.post(f"/api/pair/{s['pair_code']}").json()
    assert joined == {"session_id": sid, "role": "customer"}
    with client.websocket_connect(f"{s['ws_url']}?role=customer") as ws:
        run = run_capture(ws, on_pulse=leak_attempt)
    assert {m["type"] for m in run.received} <= {"stage", "prompt", "pulse", "done"}
    leaked = _keys(run.received, set()) & {"score", "check_id", "family"}
    assert not leaked
    events = get_events(client, sid)
    assert sum(e["type"] == "check.result" for e in events) == 10  # they did happen, for viewers only


def test_the_customer_guard_rejects_forbidden_keys_anywhere() -> None:
    assert {"score", "check_id", "family"} <= CUSTOMER_FORBIDDEN_KEYS
    assert_customer_safe({"type": "prompt", "key": "prompt.light"})
    for bad in (
        {"type": "stage", "score": 1},
        {"type": "done", "key": "prompt.done", "detail": {"check_id": "x"}},
        {"type": "pulse", "params": {"list": [{"family": "optical"}]}},
        {"type": "event", "event": {}},
    ):
        with pytest.raises(CustomerPayloadError):
            assert_customer_safe(bad)


def test_viewers_cannot_connect_as_an_unknown_role(client) -> None:
    s = create_session(client)
    with pytest.raises(Exception):  # noqa: B017 -- the socket is closed before accept
        with client.websocket_connect(f"{s['ws_url']}?role=admin") as ws:
            ws.receive_json()


# --- pulses: accepted once, a repeat is rejected, a late one is logged ok:false --------------------------------------


def test_a_pulse_ack_is_accepted_once_and_a_repeat_is_rejected(client) -> None:
    s = create_session(client)
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run = run_capture(ws, ack=lambda p: [default_ack(p), default_ack(p)])
    pulses = jsonl(bundle_dir(client, s["session_id"]) / "pulses.jsonl")
    assert len(pulses) == 10 and len(run.acks_sent) == 20
    assert len({p["pulse_id"] for p in pulses}) == 10
    assert all(p["ok"] for p in pulses)
    errors = [e for e in get_events(client, s["session_id"]) if e["type"] == "error"]
    assert [e["payload"]["code"] for e in errors] == ["duplicate_ack"] * 10


def test_a_late_ack_is_logged_ok_false(client, clock) -> None:
    s = create_session(client)

    def late(pulse: dict) -> dict:
        k = int(pulse["pulse_id"].rsplit("-", 1)[-1])
        if k == 2:
            clock.advance(10_000)  # this ack reaches the server after the pulse's deadline
        if k == 4:
            ack = default_ack(pulse)
            ack["painted"] = ack["received"] + 500  # painted 500 ms after it arrived: past expires_in_ms
            return ack
        return default_ack(pulse)

    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws, ack=late)
    pulses = {p["pulse_id"].rsplit("-", 1)[-1]: p for p in jsonl(bundle_dir(client, s["session_id"]) / "pulses.jsonl")}
    assert pulses["2"]["ok"] is False and pulses["2"]["error"] == "late"
    assert pulses["4"]["ok"] is False and pulses["4"]["error"] == "late"
    assert sum(p["ok"] for p in pulses.values()) == 8


def test_an_ack_with_a_wrong_signature_or_unknown_pulse_is_rejected(client) -> None:
    s = create_session(client)

    def forged(pulse: dict) -> list[dict]:
        bad = {**default_ack(pulse), "sig": "0" * 64}
        stranger = {**default_ack(pulse), "pulse_id": "not-a-pulse"}
        return [bad, stranger, default_ack(pulse)]

    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws, ack=forged)
    codes = [e["payload"]["code"] for e in get_events(client, s["session_id"]) if e["type"] == "error"]
    assert codes.count("bad_signature") == 10 and codes.count("unknown_pulse") == 10
    assert all(p["ok"] for p in jsonl(bundle_dir(client, s["session_id"]) / "pulses.jsonl"))


def test_pulses_are_signed_over_id_kind_params_and_session(client) -> None:
    s = create_session(client)
    released: list[dict] = []
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        run_capture(ws, on_pulse=released.append)
    assert len(released) == 10
    for p in released:
        assert p["sig"] == sign_pulse(SECRET, p["pulse_id"], p["kind"], p["params"], s["session_id"])
        assert p["source"] == "orchestrator" and p["kind"] == "light"
    modes = sorted(p["params"]["mode"] for p in released)
    assert modes == ["colour"] * 6 + ["split"] * 2 + ["white"] * 2


# --- pairing ---------------------------------------------------------------------------------------------------------


def test_pair_codes_expire_after_the_ttl(client, clock) -> None:
    s = create_session(client, product="demo", mode="live")
    code = s["pair_code"]
    assert len(code) == 6 and code.isalnum() and code.upper() == code
    assert client.post(f"/api/pair/{code}").status_code == 200
    assert client.post(f"/api/pair/{code.lower()}").status_code == 200  # typed on a phone
    clock.advance(10 * 60 * 1000 + 1)  # demo.pair_code_ttl_min = 10
    assert client.post(f"/api/pair/{code}").status_code == 410
    assert client.post("/api/pair/ZZZZZZ").status_code == 404


# --- REST: details, frames, finalize, step mode, agent ---------------------------------------------------------------


def test_details_frames_and_finalize_write_the_bundle(client) -> None:
    label = {"person": "P07", "device": "D02", "light": "dim", "kind": "genuine", "tool": None, "consent_ref": "C-7"}
    s = create_session(client, label=label)
    sid, b = s["session_id"], bundle_dir(client, s["session_id"])
    assert (
        client.post(f"/api/sessions/{sid}/details", json={"channel": "desktop_browser", "fps_median": None}).status_code
        == 204
    )
    assert client.post(f"/api/sessions/{sid}/details", json={"fps_median": 29.8}).status_code == 204
    meta_lines = [
        {
            "i": i,
            "t": 33.3 * i,
            "capture_time": None,
            "presented_frames": i,
            "w": 640,
            "h": 480,
            "file": f"{i:06d}.jpg",
            "fp_file": f"{i:06d}.jpg" if i % 5 == 0 else None,
        }
        for i in range(6)
    ]
    files = [("frames", (m["file"], b"\xff\xd8jpeg", "image/jpeg")) for m in meta_lines]
    files += [("fp", (m["file"], b"\xff\xd8fp", "image/jpeg")) for m in meta_lines if m["fp_file"]]
    r = client.post(
        f"/api/sessions/{sid}/frames", data={"meta": "\n".join(json.dumps(m) for m in meta_lines)}, files=files
    )
    assert r.status_code == 204, r.text
    assert client.post(f"/api/sessions/{sid}/finalize", json={"frames": 6, "dropped": 0}).status_code == 204

    meta = json.loads((b / "meta.json").read_text())
    assert meta["label"] == label and meta["mode"] == "superset" and meta["product"] == "lab"
    assert meta["camera_details"] == {"channel": "desktop_browser", "fps_median": 29.8}
    assert meta["finalize"] == {"frames": 6, "dropped": 0}
    assert [f["i"] for f in jsonl(b / "frames.jsonl")] == list(range(6))
    assert sorted(p.name for p in (b / "frames").iterdir()) == [m["file"] for m in meta_lines]
    assert sorted(p.name for p in (b / "fp").iterdir()) == ["000000.jpg", "000005.jpg"]
    events = get_events(client, sid)
    assert [e["type"] for e in events].count("camera.details") == 2


def test_frame_uploads_cannot_escape_the_bundle(client) -> None:
    s = create_session(client)
    meta = {"i": 0, "t": 0, "capture_time": None, "presented_frames": 0, "w": 1, "h": 1, "file": "../../evil.jpg"}
    r = client.post(
        f"/api/sessions/{s['session_id']}/frames",
        data={"meta": json.dumps(meta)},
        files=[("frames", ("../../evil.jpg", b"x", "image/jpeg"))],
    )
    assert r.status_code == 422
    assert not list(Path(client.app.state.hub.store.root).rglob("evil.jpg"))


def test_unknown_sessions_are_404(client) -> None:
    assert client.post("/api/sessions/nope/details", json={}).status_code == 404
    assert client.get("/api/sessions/nope/events").status_code == 404


def _wait_for_waiting(client, sid: str, count: int) -> list[str]:
    for _ in range(200):
        events = get_events(client, sid)
        stages = [e["payload"]["next"] for e in events if e["type"] == "orchestrator.waiting"]
        if len(stages) >= count:
            return stages
        time.sleep(0.01)
    raise AssertionError(f"orchestrator never reached waiting #{count}")


def _capture_msg(ws) -> dict:
    """Next capture message; the lab role also receives events, which this skips."""
    while (msg := ws.receive_json())["type"] == "event":
        pass
    return msg


def test_step_mode_waits_for_next_before_each_stage(client) -> None:
    s = create_session(client, mode="step", product="demo")
    sid = s["session_id"]
    nxt = f"/api/sessions/{sid}/next"
    with client.websocket_connect(f"{s['ws_url']}?role=lab&token={s['token']}") as ws:
        assert _wait_for_waiting(client, sid, 1) == ["camera"]
        assert client.post(nxt, headers=auth(client, sid)).status_code == 204
        assert _capture_msg(ws) == {"type": "stage", "stage": "camera", "prompt": None}
        ws.send_json({"type": "stage.done", "stage": "camera", "data": {}})
        assert _wait_for_waiting(client, sid, 2) == ["camera", "coach"]
        assert client.post(nxt, headers=auth(client, sid)).status_code == 204
        assert client.post(nxt, headers=auth(client, sid)).status_code in (
            204,
            409,
        )  # a double-click never skips the coach stage
        assert _capture_msg(ws)["stage"] == "coach"
        ws.send_json({"type": "stage.done", "stage": "coach", "data": {}})
        assert _wait_for_waiting(client, sid, 3) == ["camera", "coach", "pulses"]
        assert client.post(nxt, headers=auth(client, sid)).status_code == 204
        run_capture(ws)
    live = create_session(client, mode="live")
    assert (
        client.post(f"/api/sessions/{live['session_id']}/next", headers=auth(client, live["session_id"])).status_code
        == 409
    )


def test_agent_actions_need_the_console_passcode(client) -> None:
    s = create_session(client, product="demo", mode="live")
    url = f"/api/sessions/{s['session_id']}/agent"
    assert client.post(url, json={"action": "approve", "note": "looked fine"}).status_code == 401
    assert (
        client.post(url, json={"action": "approve", "note": "x"}, headers={"X-Console-Passcode": "wrong"}).status_code
        == 401
    )
    r = client.post(url, json={"action": "approve", "note": "looked fine"}, headers={"X-Console-Passcode": PASSCODE})
    assert r.status_code == 202
    actions = [e for e in get_events(client, s["session_id"]) if e["type"] == "agent.action"]
    assert actions[-1]["payload"] == {"action": "approve", "note": "looked fine"}


def test_sessions_survive_a_server_restart_for_catch_up(make_client, tmp_path) -> None:
    first = make_client(data_dir=tmp_path / "shared")
    s = create_session(first)
    before = get_events(first, s["session_id"])
    second = make_client(data_dir=tmp_path / "shared")
    assert get_events(second, s["session_id"]) == before
