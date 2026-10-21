"""Adversarial REST and WebSocket tests (SPEC 6): what a broken or hostile capture device can send."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import create_session


def bundle(client, sid: str) -> Path:
    return client.app.state.hub.store.bundle_path(sid)


def meta_line(i: int, name: str) -> dict:
    return {"i": i, "t": 33.3 * i, "capture_time": None, "presented_frames": i, "w": 4, "h": 4, "file": name}


def post_frames(
    client, sid: str, names: list[str], *, meta_names: list[str] | None = None, indices: list[int] | None = None
):
    metas = [meta_line(i, n) for i, n in zip(indices or range(len(names)), meta_names or names, strict=False)]
    return client.post(
        f"/api/sessions/{sid}/frames",
        data={"meta": "\n".join(json.dumps(m) for m in metas)},
        files=[("frames", (n, b"\xff\xd8x", "image/jpeg")) for n in names],
    )


@pytest.mark.parametrize(
    "name",
    [
        "..\\..\\evil.jpg",
        "%2e%2e%2fevil.jpg",
        "C:\\evil.jpg",
        "/tmp/evil.jpg",
        "000001.jpg\x00.png",
        "0000001.jpg",
        "000001.JPG",
        "000001.jpeg",
        "",
    ],
)
def test_every_frame_name_outside_the_six_digit_pattern_is_rejected(client, name: str) -> None:
    s = create_session(client)
    r = post_frames(client, s["session_id"], ["000000.jpg"], meta_names=[name])
    assert r.status_code == 422
    assert not (bundle(client, s["session_id"]) / "frames.jsonl").exists()
    assert not list(Path(client.app.state.hub.store.root).rglob("evil*"))


def test_a_file_part_with_a_bad_name_is_rejected_even_when_the_meta_is_fine(client) -> None:
    s = create_session(client)
    r = client.post(
        f"/api/sessions/{s['session_id']}/frames",
        data={"meta": json.dumps(meta_line(0, "000000.jpg"))},
        files=[("frames", ("..\\evil.jpg", b"x", "image/jpeg"))],
    )
    assert r.status_code == 422


def test_frame_meta_missing_fields_is_rejected(client) -> None:
    s = create_session(client)
    r = client.post(f"/api/sessions/{s['session_id']}/frames", data={"meta": json.dumps({"i": 0, "t": 1.0})})
    assert r.status_code == 422


def test_batches_arriving_out_of_order_are_read_back_in_frame_order(client) -> None:
    from pulselens.store import read_bundle

    sid = create_session(client)["session_id"]
    for batch in ([3, 4], [0, 1, 2]):  # the second upload overtook the first
        assert post_frames(client, sid, [f"{i:06d}.jpg" for i in batch], indices=batch).status_code == 204
    lines = (bundle(client, sid) / "frames.jsonl").read_text().splitlines()
    assert [json.loads(x)["i"] for x in lines] == [3, 4, 0, 1, 2]  # stored as received
    assert [f["i"] for f in read_bundle(bundle(client, sid)).frames] == [0, 1, 2, 3, 4]  # analysed in order


def test_more_files_than_the_batch_limit_is_refused_without_writing(client) -> None:
    s = create_session(client)
    names = [f"{i:06d}.jpg" for i in range(501)]
    r = post_frames(client, s["session_id"], names)
    assert r.status_code == 400
    assert not (bundle(client, s["session_id"]) / "frames").exists() or not any(
        (bundle(client, s["session_id"]) / "frames").iterdir()
    )


@pytest.mark.parametrize("endpoint", ["probe", "sensors"])
def test_jsonl_endpoints_reject_bad_json_and_store_good_lines(client, endpoint: str) -> None:
    s = create_session(client)
    sid = s["session_id"]
    assert client.post(f"/api/sessions/{sid}/{endpoint}", content=b'{"a": 1}\n{oops').status_code == 422
    assert client.post(f"/api/sessions/{sid}/{endpoint}", content=b'{"a": 1}\n\n{"a": 2}\n').status_code == 204
    lines = (bundle(client, sid) / f"{endpoint}.jsonl").read_text().splitlines()
    assert [json.loads(x)["a"] for x in lines] == [1, 2]


def test_probe_rows_are_also_emitted_as_events(client) -> None:
    s = create_session(client)
    sid = s["session_id"]
    client.post(f"/api/sessions/{sid}/probe", content=b'{"step": 0}\n{"step": 1}\n')
    events = client.get(f"/api/sessions/{sid}/events").json()["events"]
    assert [e["payload"] for e in events if e["type"] == "probe.step"] == [{"step": 0}, {"step": 1}]


def test_a_second_capture_device_is_closed_with_4409(client) -> None:
    s = create_session(client, product="demo", mode="live")
    with client.websocket_connect(f"{s['ws_url']}?role=customer"):
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect(f"{s['ws_url']}?role=customer") as second:
                second.receive_json()
        assert e.value.code == 4409


@pytest.mark.parametrize(("query", "code"), [("role=admin", 4400), ("role=presenter&from=abc", 4400)])
def test_bad_roles_and_from_values_are_closed(client, query: str, code: int) -> None:
    s = create_session(client)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"{s['ws_url']}?{query}") as ws:
            ws.receive_json()
    assert e.value.code == code


def test_an_unknown_session_socket_is_closed_with_4404(client) -> None:
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/session/0000000000000000?role=presenter") as ws:
            ws.receive_json()
    assert e.value.code == 4404


def test_garbage_websocket_messages_are_ignored(client) -> None:
    s = create_session(client)
    with client.websocket_connect(f"{s['ws_url']}?role=presenter") as ws:
        for text in ["not json", "[1, 2]", "42", '{"type": "ack"}', '{"type": "nonsense", "x": 1}']:
            ws.send_text(text)
        ws.close()
    assert client.get("/api/health").status_code == 200


@pytest.mark.xfail(strict=True, reason="events and presenter/lab sockets are unauthenticated; pairing gives the id")
def test_a_paired_customer_cannot_read_scores_through_events_or_a_presenter_socket(client) -> None:
    s = create_session(client, product="demo", mode="live")
    sid = client.post(f"/api/pair/{s['pair_code']}").json()["session_id"]  # all the customer is given
    assert client.get(f"/api/sessions/{sid}/events").status_code in (401, 403)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/session/{sid}?role=presenter") as ws:
            ws.receive_json()
