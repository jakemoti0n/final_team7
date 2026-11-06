import asyncio
from contextlib import asynccontextmanager, suppress
import hmac
import json
import logging
import os

import yaml
from pathlib import Path

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import mapdata
from .waypoints import WaypointFile, WaypointError
from .models import CommandClaim, CommandRequest, CommandResult, Settings, Telemetry, uuid_string
from .state import Store, FINAL

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


MIN_TOKEN_LENGTH = 16


def load_robot_token(settings, environ=os.environ):
    """로봇용 경로의 공유 토큰. 환경 변수 ROBOT_TOKEN → robot_token_file 순서.

    없으면 allow_no_robot_token일 때만 토큰 없이 연다(로컬 개발). 문제가 있으면 서버를 띄우지 않는다."""
    token = environ.get("ROBOT_TOKEN", "").strip()
    if not token and settings.robot_token_file:
        path = Path(settings.robot_token_file).expanduser()
        path = path if path.is_absolute() else ROOT.parent / path
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"robot_token_file cannot be read: {path} ({exc})") from exc
        if not token:
            raise RuntimeError(f"robot_token_file is empty: {path}")
    if token:
        if len(token) < MIN_TOKEN_LENGTH or any(c.isspace() for c in token):
            raise RuntimeError(f"robot token must be at least {MIN_TOKEN_LENGTH} characters without spaces")
        return token
    if not settings.allow_no_robot_token:
        raise RuntimeError("Set ROBOT_TOKEN or robot_token_file "
                           "(or allow_no_robot_token: true for local development only)")
    logging.warning("robot endpoints accept requests without a token (allow_no_robot_token)")
    return None


def create_app(settings=None, store=None, robot_token=None):
    """settings를 주지 않으면 설정 파일을 읽고 로봇 토큰도 load_robot_token으로 정한다(운영 경로).
    settings를 직접 주면(시험·내장) robot_token 인자를 그대로 쓴다. None이면 토큰 검사 없음."""
    if settings is None:
        settings = Settings.model_validate_json(Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json")).read_text())
        robot_token = load_robot_token(settings)
    expected = robot_token.encode() if robot_token else None

    def unauthorized(request):
        """로봇용 경로 인증. 맞으면 None, 아니면 401 응답 (본문을 읽기 전에 검사)"""
        if expected is None:
            return None
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(given.strip().encode(), expected):
            return None
        response = error(401, "unauthorized", "Missing or invalid robot token")
        response.headers["WWW-Authenticate"] = "Bearer"
        return response
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

    waypoint_file = None
    if settings.waypoints_yaml and map_meta is not None:
        path = Path(settings.waypoints_yaml)
        waypoint_file = WaypointFile(path if path.is_absolute() else ROOT.parent / path, map_meta)
    waypoint_lock = asyncio.Lock()   # 편집 저장과 순찰 시작(경로 고정)이 겹치지 않게

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
        if denied := unauthorized(request):
            return denied
        raw, problem = await read_json(request)
        if problem:
            return problem
        try:
            payload = Telemetry.model_validate(raw)
        except (ValidationError, ValueError):
            return error(422, "invalid_payload", "Payload does not match telemetry contract v1/v2/v3")
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
            return error(422, "invalid_command", "command must be pause, resume, start or stop")
        name, route = command.command, None
        async with waypoint_lock:
            if name in ("start", "stop"):
                # 시작·종료는 로봇 컴퓨터의 Bridge가 실행한다. 이전 Bridge(v1·v2)는 모르는 명령이므로 쌓지 않음
                if store.command and store.command["stage"] not in FINAL:
                    return error(409, "command_in_progress", "Another command is still in progress")
                if store.connection()[0] != "connected":
                    return error(409, "bridge_not_connected", "Bridge is not connected")
                launcher = store.launcher()
                if launcher is None or name not in launcher["commands"]:
                    return error(409, "bridge_unsupported", "Connected Bridge cannot start or stop patrol; update relay_prog")
                if name == "stop" and launcher["state"] != "running":
                    return error(409, "patrol_not_running", "No Bridge-started patrol_node is running")
                if name == "start":
                    if store.patrol_running():
                        return error(409, "patrol_already_running", "A patrol_node is already running")
                    if waypoint_file is None:
                        return error(404, "waypoints_not_configured", "Set map_yaml and waypoints_yaml")
                    try:
                        route = waypoint_file.route()   # 이 순간의 서버 YAML을 명령에 고정
                    except WaypointError as exc:
                        return error(409, exc.code, str(exc))
                    except (OSError, ValueError, yaml.YAMLError) as exc:
                        logging.error("waypoints not loaded: %s", exc)
                        return error(503, "waypoints_unavailable", "Waypoint file cannot be read")
            status, body = store.issue(name, route)
        if status != 202:
            return error(status, *body)
        command_signal.set()
        publish()
        return JSONResponse(body, status_code=202)

    @app.get("/api/v1/commands/next")
    async def next_command(request: Request, robot_id: str = "", bridge_session_id: str = "", wait_s: float = 0.):
        if denied := unauthorized(request):
            return denied
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
        if denied := unauthorized(request):
            return denied
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
        if denied := unauthorized(request):
            return denied
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
        if waypoint_file is not None:
            try:
                return {**map_meta, "waypoints": [dict(name=str(w["name"]), type=str(w["type"]), x=float(w["x"]), y=float(w["y"])) for w in waypoint_file.document()["waypoints"]]}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                logging.error("waypoints not loaded: %s", exc)
                return error(503, "waypoints_unavailable", "Waypoint file cannot be read")
        return map_meta

    @app.get("/api/v1/waypoints")
    async def get_waypoints():
        if waypoint_file is None:
            return error(404, "waypoints_not_configured", "Set map_yaml and waypoints_yaml")
        try:
            return waypoint_file.document()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logging.error("waypoints not loaded: %s", exc)
            return error(503, "waypoints_unavailable", "Waypoint file cannot be read")

    @app.put("/api/v1/waypoints")
    async def change_waypoints(request: Request):
        if waypoint_file is None:
            return error(404, "waypoints_not_configured", "Set map_yaml and waypoints_yaml")
        raw, problem = await read_json(request)
        if problem:
            return problem
        async with waypoint_lock:
            # 판단 근거는 Bridge가 보고한 순찰 상태와 노드 실행 상태. 순찰 시작·종료 명령이 처리 중이어도 잠근다
            starting = (store.command and store.command["command"] in ("start", "stop")
                        and store.command["stage"] not in FINAL)
            if store.patrol_running() or starting:
                return error(409, "patrol_active", "Waypoint changes are available after patrol finishes")
            try:
                return waypoint_file.change(raw)
            except WaypointError as exc:
                return error(409 if exc.code in ("revision_conflict", "invalid_route", "not_found") else 422, exc.code, str(exc))
            except (OSError, yaml.YAMLError) as exc:
                logging.error("waypoints not saved: %s", exc)
                return error(503, "waypoints_unavailable", "Waypoint file cannot be saved")

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
