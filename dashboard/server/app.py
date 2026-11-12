import asyncio
from contextlib import asynccontextmanager, suppress
import hmac
import json
import logging
import os
import secrets
import time

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
STREAM_TICKET_TTL_S = 30      # 화면이 받은 WebSocket 입장표의 유효 시간
STREAM_TICKET_LIMIT = 1000    # 쓰지 않고 쌓인 입장표 상한


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
    base_store = store or Store(settings)
    robots = {}           # robot_id → Robot. 넣은 순서 = 화면 목록 순서 (기본 로봇, 설정, 자동 등록 순)
    maps = {}             # (map_yaml, waypoints_yaml) → (메타, PNG) 또는 None. 같은 파일은 한 번만 읽는다
    waypoint_files = {}   # (waypoint 실제 경로, map_yaml) → (WaypointFile, Lock). 같은 파일을 쓰는 로봇끼리 공유

    class Robot:
        """로봇 하나의 상태·구독자·명령 신호·지도·waypoint 파일"""
        def __init__(self, robot_id, robot_store):
            self.id, self.store = robot_id, robot_store
            self.subscribers = set()
            self.command_signal = asyncio.Event()   # 새 명령이 생기면 기다리던 commands/next를 깨운다
            override = settings.robots.get(robot_id)
            map_yaml = (override and override.map_yaml) or settings.map_yaml
            waypoints_yaml = (override and override.waypoints_yaml) or settings.waypoints_yaml
            self.map_meta, self.map_png = load_map(map_yaml, waypoints_yaml)
            self.map_key = map_yaml if self.map_meta is not None else None   # 같은 지도인지 비교용
            if self.map_meta is not None:
                # 지도 그림 주소에 로봇을 붙인다 (로봇마다 지도가 다를 수 있음)
                self.map_meta = {**self.map_meta, "image": f"/api/v1/map.png?robot_id={robot_id}"}
            robot_store.map_available = self.map_meta is not None
            self.waypoint_file, self.lock = None, asyncio.Lock()
            if waypoints_yaml and self.map_meta is not None:
                path = Path(waypoints_yaml)
                path = (path if path.is_absolute() else ROOT.parent / path).resolve()
                key = (path, map_yaml)
                if key not in waypoint_files:
                    waypoint_files[key] = (WaypointFile(path, self.map_meta), asyncio.Lock())
                # 편집 저장과 순찰 시작(경로 고정)이 겹치지 않게 같은 파일이면 같은 잠금
                self.waypoint_file, self.lock = waypoint_files[key]

        def summary(self):
            status, _ = self.store.connection()
            return dict(robot_id=self.id, status=status, last_received_at=self.store.received_at)

    def load_map(map_yaml, waypoints_yaml):
        if not map_yaml:
            return None, None
        key = (map_yaml, waypoints_yaml)
        if key not in maps:
            try:
                maps[key] = mapdata.load(map_yaml, waypoints_yaml, base=ROOT.parent)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logging.error("map not loaded: %s", exc)
                maps[key] = None
        return maps[key] or (None, None)

    def register(robot_id, robot_store=None):
        robots[robot_id] = Robot(robot_id, robot_store or Store(
            settings, base_store.monotonic, base_store.utc, robot_id=robot_id))
        return robots[robot_id]

    register(settings.robot_id, base_store)
    for robot_id in settings.robots:
        if robot_id not in robots:
            register(robot_id)

    def find(robot_id):
        """화면 요청의 로봇. 비우면 기본 로봇, 모르는 로봇이면 None"""
        return robots.get(robot_id or settings.robot_id)

    def robot_list(viewer=None):
        """로봇 목록. viewer를 주면 같은 지도를 쓰는 다른 로봇의 위치도 넣는다 (지도가 다르면 좌표가 맞지 않음)"""
        items = []
        for robot in robots.values():
            item = robot.summary()
            if viewer is not None and robot is not viewer:
                same_map = viewer.map_key is not None and robot.map_key == viewer.map_key
                item["pose"] = robot.store.pose_view() if same_map else None
            items.append(item)
        return items

    def view(robot):
        return {**robot.store.snapshot(), "robots": robot_list(robot)}

    def publish(robot):
        state = view(robot)
        for queue in tuple(robot.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(state)
        return state

    def unknown_robot():
        return error(404, "unknown_robot", "No telemetry has been received from this robot_id")

    def patrol_busy(robot):
        """순찰 노드가 돌거나 순찰 시작·종료 명령이 처리 중 (waypoint 편집 잠금)"""
        command = robot.store.command
        starting = command and command["command"] in ("start", "stop") and command["stage"] not in FINAL
        return robot.store.patrol_running() or bool(starting)

    async def ticker():
        while True:
            await asyncio.sleep(1)
            for robot in tuple(robots.values()):
                publish(robot)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(ticker())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(lifespan=lifespan)
    app.state.store, app.state.robots = base_store, robots

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
        robot = robots.get(payload.robot_id)
        if robot is None:
            # 처음 보는 로봇은 자동 등록 (토큰은 위에서 확인). 상한을 넘으면 받지 않는다
            if len(robots) >= settings.max_robots:
                return error(429, "too_many_robots", "Robot limit reached; raise max_robots or restart the server")
            robot = register(payload.robot_id)
            logging.info("robot registered: %s", payload.robot_id)
        response = robot.store.accept(payload)
        if response["accepted"]:
            publish(robot)
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
        robot = find(command.robot_id)
        if robot is None:
            return unknown_robot()
        store, waypoint_file = robot.store, robot.waypoint_file
        name, route = command.command, None
        async with robot.lock:
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
        robot.command_signal.set()
        publish(robot)
        return JSONResponse(body, status_code=202)

    @app.get("/api/v1/commands/next")
    async def next_command(request: Request, robot_id: str = "", bridge_session_id: str = "", wait_s: float = 0.):
        if denied := unauthorized(request):
            return denied
        try:
            session = uuid_string(bridge_session_id)
        except ValueError:
            return error(422, "invalid_payload", "bridge_session_id must be a UUID")
        wait = min(max(wait_s, 0.), 10.)
        robot = robots.get(robot_id)
        if robot is None:
            # 아직 텔레메트리를 보내지 않은 로봇: 줄 명령이 없다. 바로 답하면 Bridge가 쉬지 않고 다시 물으므로 기다린 뒤 답한다
            await asyncio.sleep(wait)
            return Response(status_code=204)
        store = robot.store
        if session in store.retired:
            return error(409, "retired_session", "Bridge session was replaced")
        deadline = asyncio.get_running_loop().time() + wait
        while True:
            command = store.take_command(session)
            if command:
                robot.command_signal.clear()
                publish(robot)
                return command
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return Response(status_code=204)
            with suppress(TimeoutError):
                await asyncio.wait_for(robot.command_signal.wait(), timeout=min(remaining, 0.2))

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
        robot = robots.get(claim.robot_id)
        if robot is None:
            return error(409, "unknown_robot", "Unknown robot_id")
        if not robot.store.claim(request_id, claim.bridge_session_id):
            publish(robot)
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
        robot = robots.get(result.robot_id)
        if robot is None:
            return error(409, "unknown_robot", "Unknown robot_id")
        reply = robot.store.apply_result(result)
        publish(robot)
        return reply

    @app.get("/api/v1/robots")
    async def robot_index():
        return {"default": settings.robot_id, "robots": robot_list()}

    @app.get("/api/v1/map")
    async def map_info(robot_id: str = ""):
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.map_meta is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        if robot.waypoint_file is not None:
            try:
                return {**robot.map_meta, "waypoints": [dict(name=str(w["name"]), type=str(w["type"]), x=float(w["x"]), y=float(w["y"])) for w in robot.waypoint_file.document()["waypoints"]]}
            except (OSError, ValueError, yaml.YAMLError) as exc:
                logging.error("waypoints not loaded: %s", exc)
                return error(503, "waypoints_unavailable", "Waypoint file cannot be read")
        return robot.map_meta

    @app.get("/api/v1/waypoints")
    async def get_waypoints(robot_id: str = ""):
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.waypoint_file is None:
            return error(404, "waypoints_not_configured", "Set map_yaml and waypoints_yaml")
        try:
            return robot.waypoint_file.document()
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logging.error("waypoints not loaded: %s", exc)
            return error(503, "waypoints_unavailable", "Waypoint file cannot be read")

    @app.put("/api/v1/waypoints")
    async def change_waypoints(request: Request, robot_id: str = ""):
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.waypoint_file is None:
            return error(404, "waypoints_not_configured", "Set map_yaml and waypoints_yaml")
        raw, problem = await read_json(request)
        if problem:
            return problem
        async with robot.lock:
            # 판단 근거는 Bridge가 보고한 순찰 상태와 노드 실행 상태. 순찰 시작·종료 명령이 처리 중이어도 잠근다.
            # 같은 waypoint 파일을 쓰는 다른 로봇이 순찰 중이어도 잠근다
            if any(patrol_busy(other) for other in robots.values() if other.waypoint_file is robot.waypoint_file):
                return error(409, "patrol_active", "Waypoint changes are available after patrol finishes")
            try:
                return robot.waypoint_file.change(raw)
            except WaypointError as exc:
                return error(409 if exc.code in ("revision_conflict", "invalid_route", "not_found") else 422, exc.code, str(exc))
            except (OSError, yaml.YAMLError) as exc:
                logging.error("waypoints not saved: %s", exc)
                return error(503, "waypoints_unavailable", "Waypoint file cannot be saved")

    @app.get("/api/v1/map.png")
    async def map_image(robot_id: str = ""):
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.map_png is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return Response(robot.map_png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/state")
    async def state(robot_id: str = ""):
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        return view(robot)

    # WebSocket 입장표. Safari(iPhone·iPad)는 WebSocket 연결에 basic auth를 싣지 않아
    # Caddy가 401을 주고 로그인 창이 반복된다. 그래서 stream은 basic auth에서 빼고,
    # basic auth 뒤에 있는 이 경로에서 받은 일회용 입장표로만 들어오게 한다.
    stream_tickets = {}   # 입장표 → 만료 시각(monotonic)

    @app.post("/api/v1/stream-ticket")
    async def stream_ticket():
        now = time.monotonic()
        for old_ticket in [t for t, until in stream_tickets.items() if until <= now]:
            del stream_tickets[old_ticket]
        if len(stream_tickets) >= STREAM_TICKET_LIMIT:
            return error(429, "too_many_tickets", "Too many unused stream tickets")
        ticket = secrets.token_urlsafe(24)
        stream_tickets[ticket] = now + STREAM_TICKET_TTL_S
        return JSONResponse({"ticket": ticket}, headers={"Cache-Control": "no-store"})

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket, robot_id: str = "", ticket: str = ""):
        if stream_tickets.pop(ticket, 0) <= time.monotonic():
            await websocket.close(code=4401, reason="invalid_ticket")   # accept 전이면 403으로 거절된다
            return
        robot = find(robot_id)
        await websocket.accept()
        if robot is None:
            await websocket.close(code=4404, reason="unknown_robot")
            return
        queue = asyncio.Queue(maxsize=1)
        robot.subscribers.add(queue)
        queue.put_nowait(view(robot))

        async def watch_disconnect():
            while True:
                if (await websocket.receive())["type"] == "websocket.disconnect":
                    return

        async def send():
            while True:
                # 막힌 소켓은 끊는다. 대기 중인 스냅샷은 한 개를 넘지 않는다
                await asyncio.wait_for(websocket.send_json(await queue.get()), timeout=3)

        tasks = [asyncio.create_task(send()), asyncio.create_task(watch_disconnect())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            robot.subscribers.discard(queue)
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
