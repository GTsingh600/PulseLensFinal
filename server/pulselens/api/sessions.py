"""Session and pairing REST API (SPEC 6). Handlers are async so every event is emitted on the event loop."""

from __future__ import annotations

import asyncio
import hmac
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError

from pulselens.hub import Hub, SessionRuntime
from pulselens.models import AgentRequest, FrameMeta, PairJoined, SessionCreate, SessionCreated
from pulselens.pairing import PairCodeExpired
from pulselens.store import FRAME_NAME

router = APIRouter(prefix="/api")
NO_CONTENT = Response(status_code=204)


def _hub(request: Request) -> Hub:
    return request.app.state.hub


def _runtime(request: Request, session_id: str) -> SessionRuntime:
    rt = _hub(request).runtime(session_id)
    if rt is None:
        raise HTTPException(404, "unknown session")
    return rt


def _token(request: Request, session_id: str, header: str | None) -> None:
    """Scores and stage control belong to whoever created the session (SessionCreated.token)."""
    token = header or request.query_params.get("token")
    if not _hub(request).token_ok(session_id, token):
        raise HTTPException(401, "session token required (X-Session-Token)")


def _passcode(request: Request, passcode: str | None) -> None:
    expected = _hub(request).settings.console_passcode
    if not passcode or not hmac.compare_digest(passcode.encode(), expected.encode()):
        raise HTTPException(401, "console passcode required (prototype-level protection)")


@router.post("/sessions")
async def create_session(request: Request, body: SessionCreate) -> SessionCreated:
    return _hub(request).create(body)


@router.post("/pair/{code}")
async def pair(request: Request, code: str) -> PairJoined:
    try:
        session_id = _hub(request).pairing.resolve(code)
    except PairCodeExpired:
        raise HTTPException(410, "pair code expired; start a new session") from None
    except KeyError:
        raise HTTPException(404, "unknown pair code") from None
    return PairJoined(session_id=session_id)


@router.post("/sessions/{session_id}/details", status_code=204)
async def details(request: Request, session_id: str, partial: Annotated[dict[str, Any], Body()]) -> Response:
    rt = _runtime(request, session_id)
    _hub(request).store.merge_details(session_id, partial)
    rt.bus.emit("camera.details", partial)
    return NO_CONTENT


def _lines(text: str) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"bad JSON line: {e}") from None


@router.post("/sessions/{session_id}/probe", status_code=204)
async def probe(request: Request, session_id: str) -> Response:
    rt = _runtime(request, session_id)
    rows = _lines((await request.body()).decode())
    _hub(request).store.append_jsonl(session_id, "probe.jsonl", rows)
    for row in rows:
        rt.bus.emit("probe.step", row)
    return NO_CONTENT


@router.post("/sessions/{session_id}/sensors", status_code=204)
async def sensors(request: Request, session_id: str) -> Response:
    _runtime(request, session_id)
    _hub(request).store.append_jsonl(session_id, "sensors.jsonl", _lines((await request.body()).decode()))
    return NO_CONTENT


@router.post("/sessions/{session_id}/frames", status_code=204)
async def frames(request: Request, session_id: str) -> Response:
    """Multipart batch: `meta` = frames.jsonl lines, `frames` = working JPEGs, `fp` = fingerprint JPEGs."""
    _runtime(request, session_id)
    store = _hub(request).store
    async with request.form(max_files=500, max_fields=10) as form:
        try:
            metas = [FrameMeta.model_validate(row) for row in _lines(str(form.get("meta") or ""))]
        except ValidationError as e:
            raise HTTPException(422, f"bad frame meta: {e.errors()[0]['msg']}") from None
        files = [(folder, f) for folder in ("frames", "fp") for f in form.getlist(folder) if hasattr(f, "read")]
        names = [m.file for m in metas] + [m.fp_file for m in metas if m.fp_file] + [f.filename or "" for _, f in files]
        if bad := [n for n in names if not FRAME_NAME.match(n)]:
            raise HTTPException(422, f"bad frame file name {bad[0]!r}")
        for folder, f in files:
            store.save_frame(session_id, folder, f.filename or "", await f.read())
    store.append_jsonl(session_id, "frames.jsonl", [m.model_dump() for m in metas])
    return NO_CONTENT


@router.post("/sessions/{session_id}/finalize", status_code=204)
async def finalize(request: Request, session_id: str, summary: Annotated[dict[str, Any], Body()]) -> Response:
    _runtime(request, session_id)
    _hub(request).store.finalize(session_id, summary)
    return NO_CONTENT


@router.post("/sessions/{session_id}/next", status_code=204)
async def next_stage(
    request: Request, session_id: str, x_session_token: Annotated[str | None, Header()] = None
) -> Response:
    """Step-through mode: release the stage the orchestrator is waiting at (SPEC 14.1). Only valid while it
    waits, so a double-click never skips a stage the audience hasn't seen explained."""
    rt = _runtime(request, session_id)
    _token(request, session_id, x_session_token)
    if rt.mode != "step":
        raise HTTPException(409, "session is not in step mode")
    if rt.waiting_for is None:
        raise HTTPException(409, "the orchestrator is not waiting for Next")
    rt.next_stage.set()
    return NO_CONTENT


@router.post("/sessions/{session_id}/agent", status_code=202)
async def agent(
    request: Request,
    session_id: str,
    body: AgentRequest,
    x_console_passcode: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Logged now; fire_light, fire_tilt and take_photo act on the session from M3.3."""
    _passcode(request, x_console_passcode)
    rt = _runtime(request, session_id)
    rt.bus.emit("agent.action", {"action": body.action, "note": body.note})
    return {"status": "logged"}


def _analyse(path: Path) -> dict[str, Any]:
    from pulselens.cli import run_analysis
    from pulselens.store import read_bundle

    return run_analysis(read_bundle(path))[2]


@router.post("/sessions/{session_id}/analyze", status_code=202)
async def analyze(
    request: Request, session_id: str, x_session_token: Annotated[str | None, Header()] = None
) -> dict[str, str]:
    """Run every check on the saved bundle in a worker thread (the same analysis as `cli analyze`)."""
    _runtime(request, session_id)
    _token(request, session_id, x_session_token)
    hub = _hub(request)
    task = hub.analyses.get(session_id)
    if task is None or task.done():
        path = hub.store.bundle_path(session_id)
        hub.analyses[session_id] = asyncio.get_running_loop().create_task(asyncio.to_thread(_analyse, path))
    return {"status": "running"}


@router.get("/sessions/{session_id}/report")
async def report(
    request: Request, session_id: str, x_session_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """Results for the Lab: `running`, `error`, `none` (never analysed) or `done` with qc and checks."""
    _runtime(request, session_id)
    _token(request, session_id, x_session_token)
    hub = _hub(request)
    task = hub.analyses.get(session_id)
    if task is not None and not task.done():
        return {"status": "running"}
    if task is not None and task.exception() is not None:
        return {"status": "error", "error": f"{type(task.exception()).__name__}: {task.exception()}"}
    file = hub.store.bundle_path(session_id) / "analysis" / "checks.json"
    if not file.exists():
        return {"status": "none"}
    return {"status": "done", **json.loads(file.read_text(encoding="utf-8"))}


@router.get("/sessions/{session_id}/events")
async def events(
    request: Request,
    session_id: str,
    from_seq: Annotated[int, Query(alias="from", ge=0)] = 0,
    x_session_token: Annotated[str | None, Header()] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Catch-up for reconnect and replay: events with seq >= `from`. Events carry scores, so they need the token."""
    rt = _runtime(request, session_id)
    _token(request, session_id, x_session_token)
    return {"events": [e.model_dump() for e in rt.bus.since(from_seq)]}
