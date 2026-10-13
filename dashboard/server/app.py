import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import mapdata
from .models import CommandClaim, CommandRequest, CommandResult, Settings, Telemetry, uuid_string
from .state import Store

ROOT = Path(__file__).resolve().parents[1]


def error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


async def read_json(request):
    """(본문, 오류 응답). 텔레메트리와 같은 규칙: JSON, 8192바이트 이하."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return None, error(415, "unsupported_media_type", "Expected application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 8192:
            return None, error(413, "payload_too_large", "Maximum request body is 8192 bytes")
        body.extend(chunk)
    try:
        return json.loads(body.decode("utf-8")), None
    except (ValueError, UnicodeError, RecursionError):
        return None, error(400, "invalid_json", "Malformed UTF-8 JSON")


def create_app(settings=None, store=None):
    settings = settings or Settings.model_validate_json(Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json")).read_text())
    store = store or Store(settings)
    subscribers = set()
    command_signal = asyncio.Event()   # 새 명령이 생기면 기다리던 commands/next를 깨운다
    map_meta, map_png = None, None
    if settings.map_yaml:
        try:
            map_meta, map_png = mapdata.load(settings.map_yaml, settings.waypoints_yaml, base=ROOT.parent)
            store.map_available = True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logging.error("map not loaded: %s", exc)

    def publish():
        state = store.snapshot()
        for queue in tuple(subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(state)
        return state

    async def ticker():
        while True:
            await asyncio.sleep(1)
            publish()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ticker())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(lifespan=lifespan)
    app.state.store, app.state.subscribers = store, subscribers

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logging.exception("Dashboard server error", exc_info=exc)
        return error(500, "server_error", "Internal server error")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.post("/api/v1/telemetry")
    async def receive(request: Request):
        raw, problem = await read_json(request)
        if problem:
            return problem
        try:
            payload = Telemetry.model_validate(raw)
        except (ValidationError, ValueError):
            return error(422, "invalid_payload", "Payload does not match telemetry contract v1")
        if payload.robot_id != settings.robot_id:
            return error(409, "robot_id_mismatch", "Unexpected robot_id")
        response = store.accept(payload)
        if response["accepted"]:
            publish()
        return response

    @app.post("/api/v1/commands")
    async def issue(request: Request):
        raw, problem = await read_json(request)
        if problem:
            return problem
        try:
            command = CommandRequest.model_validate(raw)
        except (ValidationError, ValueError):
            return error(422, "invalid_command", "command must be pause or resume")
        status, body = store.issue(command.command)
        if status != 202:
            return error(status, *body)
        command_signal.set()
        publish()
        return JSONResponse(body, status_code=202)

    @app.get("/api/v1/commands/next")
    async def next_command(robot_id: str = "", bridge_session_id: str = "", wait_s: float = 0.):
        if robot_id != settings.robot_id:
            return error(409, "robot_id_mismatch", "Unexpected robot_id")
        try:
            session = uuid_string(bridge_session_id)
        except ValueError:
            return error(422, "invalid_payload", "bridge_session_id must be a UUID")
        if session in store.retired:
            return error(409, "retired_session", "Bridge session was replaced")
        deadline = asyncio.get_running_loop().time() + min(max(wait_s, 0.), 10.)
        while True:
            command = store.take_command(session)
            if command:
                command_signal.clear()
                publish()
                return command
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return Response(status_code=204)
            with suppress(TimeoutError):
                await asyncio.wait_for(command_signal.wait(), timeout=min(remaining, 0.2))

    @app.post("/api/v1/commands/{request_id}/claim")
    async def command_claim(request_id: str, request: Request):
        raw, problem = await read_json(request)
        if problem:
            return problem
        try:
            claim = CommandClaim.model_validate(raw)
        except (ValidationError, ValueError):
            return error(422, "invalid_payload", "Claim does not match the command contract")
        if claim.robot_id != settings.robot_id:
            return error(409, "robot_id_mismatch", "Unexpected robot_id")
        if not store.claim(request_id, claim.bridge_session_id):
            publish()
            return error(409, "command_closed", "Command is no longer valid")
        return {"claimed": True}

    @app.post("/api/v1/commands/{request_id}/result")
    async def command_result(request_id: str, request: Request):
        raw, problem = await read_json(request)
        if problem:
            return problem
        try:
            result = CommandResult.model_validate(raw)
        except (ValidationError, ValueError):
            return error(422, "invalid_payload", "Result does not match the command contract")
        if result.request_id != request_id:
            return error(422, "invalid_payload", "request_id does not match the path")
        if result.robot_id != settings.robot_id:
            return error(409, "robot_id_mismatch", "Unexpected robot_id")
        reply = store.apply_result(result)
        publish()
        return reply

    @app.get("/api/v1/map")
    async def map_info():
        if map_meta is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return map_meta

    @app.get("/api/v1/map.png")
    async def map_image():
        if map_png is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return Response(map_png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/state")
    async def state():
        return store.snapshot()

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket):
        await websocket.accept()
        queue = asyncio.Queue(maxsize=1)
        subscribers.add(queue)
        queue.put_nowait(store.snapshot())

        async def watch_disconnect():
            while True:
                if (await websocket.receive())["type"] == "websocket.disconnect":
                    return

        async def send():
            while True:
                # A stalled socket is disconnected; queued snapshots never exceed one.
                await asyncio.wait_for(websocket.send_json(await queue.get()), timeout=3)

        tasks = [asyncio.create_task(send()), asyncio.create_task(watch_disconnect())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            subscribers.discard(queue)
            for task in tasks:
                task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError, TimeoutError):
                    await task
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close()

    dist = ROOT / "ui" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/")
    @app.get("/demo")
    async def ui():
        if not (dist / "index.html").exists():
            return error(503, "server_error", "Build dashboard/ui first; see README")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
