"""WebSocket /ws/session/{id}?role=customer|lab|presenter[&from=seq] (SPEC 6). Roles are explained in hub.py."""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pulselens.hub import ROLES, Connection, Hub

router = APIRouter()

CLOSE_UNKNOWN_SESSION = 4404
CLOSE_BAD_ROLE = 4400
CLOSE_CAPTURE_TAKEN = 4409


@router.websocket("/ws/session/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    hub: Hub = ws.app.state.hub
    role = ws.query_params.get("role")
    from_param = ws.query_params.get("from")
    rt = hub.runtime(session_id)
    if rt is None:
        await ws.close(CLOSE_UNKNOWN_SESSION)
        return
    if role not in ROLES or (from_param is not None and not from_param.isdigit()):
        await ws.close(CLOSE_BAD_ROLE)
        return
    await ws.accept()
    conn = Connection(ws, role)  # type: ignore[arg-type]
    if not rt.attach(conn, int(from_param) if from_param is not None else None):
        await ws.close(CLOSE_CAPTURE_TAKEN)
        return
    pump = asyncio.create_task(conn.pump())
    try:
        while True:
            text = await ws.receive_text()
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict):
                rt.on_message(conn, msg)
    except WebSocketDisconnect:
        pass
    finally:
        rt.detach(conn)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(pump, 1.0)
        pump.cancel()
