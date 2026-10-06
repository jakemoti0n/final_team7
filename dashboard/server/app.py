import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import Settings, Telemetry
from .state import Store

ROOT = Path(__file__).resolve().parents[1]


def error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(settings=None, store=None):
    settings = settings or Settings.model_validate_json(Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json")).read_text())
    store = store or Store(settings)
    subscribers = set()

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
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return error(415, "unsupported_media_type", "Expected application/json")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                return error(413, "payload_too_large", "Maximum request body is 8192 bytes")
            body.extend(chunk)
        try:
            raw = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            return error(400, "invalid_json", "Malformed UTF-8 JSON")
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
