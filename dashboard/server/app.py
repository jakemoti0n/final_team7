import asyncio
from contextlib import asynccontextmanager, suppress
import hmac
import json
import logging
import os
import secrets
import time
from urllib.parse import urlsplit

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
from .users import UserError, UserStore, token_hash

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
SESSION_COOKIE = "limbo_session"
SESSION_RECHECK_S = 30        # 열린 실시간 연결이 로그인(세션)이 아직 유효한지 다시 보는 간격
LOGIN_WINDOW_S = 300          # 로그인 실패를 세는 기간
LOGIN_LIMIT = 10              # 같은 IP·같은 아이디로 기간 안에 허용하는 실패 횟수

# 누가 무엇을 했는지 (로그인·회원 관리·명령·waypoint). uvicorn은 루트 로거의 INFO를 찍지 않으므로 따로 둔다
audit = logging.getLogger("dashboard.audit")
if not audit.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s audit: %(message)s"))
    audit.addHandler(_handler)
    audit.setLevel(logging.INFO)
    audit.propagate = False


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


def load_users(settings, environ=os.environ):
    """화면 로그인용 사용자 DB. 계정이 하나도 없으면 ADMIN_USERNAME/ADMIN_PASSWORD로 첫 관리자를 만든다.

    users_db가 없으면 allow_no_login일 때만 로그인 없이 연다(로컬 개발). 문제가 있으면 서버를 띄우지 않는다."""
    if not settings.users_db:
        if not settings.allow_no_login:
            raise RuntimeError("Set users_db (or allow_no_login: true for local development only)")
        logging.warning("dashboard screen is open without login (allow_no_login)")
        return None
    path = Path(settings.users_db).expanduser()
    path = path if path.is_absolute() else ROOT.parent / path
    users = UserStore(str(path), settings.session_idle_s, settings.session_max_s)
    users.bootstrap(environ)
    users.purge_sessions()
    return users


def create_app(settings=None, store=None, robot_token=None, users=None):
    """settings를 주지 않으면 설정 파일을 읽고 로봇 토큰·사용자 DB도 설정대로 연다(운영 경로).
    settings를 직접 주면(시험·내장) robot_token·users 인자를 그대로 쓴다. None이면 그 검사를 하지 않는다."""
    if settings is None:
        settings = Settings.model_validate_json(Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json")).read_text())
        robot_token = load_robot_token(settings)
        users = load_users(settings)
        owns_users = users is not None   # 직접 연 DB만 끌 때 닫는다 (시험이 넘긴 DB는 시험이 닫음)
    else:
        owns_users = False
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

    # ---- 화면 로그인 (로봇용 경로는 위의 토큰만 쓴다) ----

    def cross_site(request):
        """다른 사이트에서 보낸 요청인가 (CSRF 방어의 한 겹). 브라우저가 붙이는 Origin이 이 서버 주소와 다르면 거절"""
        origin = request.headers.get("origin")
        return origin is not None and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()

    def require_user(request, allow_password_change=False):
        """화면용 경로 인증. (사용자, None) 또는 (None, 오류 응답). 로그인 없이 연 서버면 (None, None)"""
        if request.method not in ("GET", "HEAD") and cross_site(request):
            return None, error(403, "cross_site_request", "Request from another site was rejected")
        if users is None:
            return None, None
        user = users.session_user(request.cookies.get(SESSION_COOKIE))
        if user is None:
            return None, error(401, "login_required", "Log in first")
        if user["must_change_password"] and not allow_password_change:
            return None, error(403, "password_change_required", "Change your password first")
        return user, None

    def login_disabled():
        return error(404, "login_disabled", "This server runs without login (allow_no_login)")

    def user_error(exc):
        return error(exc.status, exc.code, exc.message)

    def who(user):
        return user["username"] if user else None

    def me_view(user):
        return dict(id=user["id"], username=user["username"], display_name=user["display_name"],
                    must_change_password=user["must_change_password"])

    def client_ip(request):
        # 서버는 Caddy 뒤에서만 열린다. Caddy는 밖에서 온 X-Forwarded-For를 버리고 실제 주소로 새로 붙인다
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        return forwarded or (request.client.host if request.client else "")

    def set_session_cookie(response, request, token):
        # Caddy 뒤(https)면 Secure. 로컬 http 시험에서도 로그인할 수 있게 http면 빼 둔다
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
        response.set_cookie(SESSION_COOKIE, token, max_age=int(settings.session_max_s), path="/",
                            httponly=True, secure=secure, samesite="strict")

    login_failures = {}   # (IP, 아이디) → 최근 실패 시각들(monotonic)
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
        if owns_users:
            users.close()   # WAL 내용을 DB 파일에 반영하고 닫는다

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
        user, denied = require_user(request)
        if denied:
            return denied
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
            status, body = store.issue(name, route, issued_by=who(user))
        if status != 202:
            return error(status, *body)
        audit.info("command %s for %s by %s", name, robot.id, who(user))
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
    async def robot_index(request: Request):
        if (denied := require_user(request)[1]):
            return denied
        return {"default": settings.robot_id, "robots": robot_list()}

    @app.get("/api/v1/map")
    async def map_info(request: Request, robot_id: str = ""):
        if (denied := require_user(request)[1]):
            return denied
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
    async def get_waypoints(request: Request, robot_id: str = ""):
        if (denied := require_user(request)[1]):
            return denied
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
        user, denied = require_user(request)
        if denied:
            return denied
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
                document = robot.waypoint_file.change(raw)
                audit.info("waypoints %s changed for %s by %s", raw.get("action") if isinstance(raw, dict) else None,
                           robot.id, who(user))
                return document
            except WaypointError as exc:
                return error(409 if exc.code in ("revision_conflict", "invalid_route", "not_found") else 422, exc.code, str(exc))
            except (OSError, yaml.YAMLError) as exc:
                logging.error("waypoints not saved: %s", exc)
                return error(503, "waypoints_unavailable", "Waypoint file cannot be saved")

    @app.get("/api/v1/map.png")
    async def map_image(request: Request, robot_id: str = ""):
        if (denied := require_user(request)[1]):
            return denied
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.map_png is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return Response(robot.map_png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/state")
    async def state(request: Request, robot_id: str = ""):
        if (denied := require_user(request)[1]):
            return denied
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        return view(robot)

    # ---- 로그인·회원 관리 (계정은 모두 관리자 한 등급) ----

    @app.get("/api/v1/auth/me")
    async def auth_me(request: Request):
        if users is None:
            return {"login_required": False, "user": None}
        user, denied = require_user(request, allow_password_change=True)
        if denied:
            return denied
        return JSONResponse({"login_required": True, "user": me_view(user)}, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/auth/login")
    async def auth_login(request: Request):
        if cross_site(request):
            return error(403, "cross_site_request", "Request from another site was rejected")
        if users is None:
            return login_disabled()
        raw, problem = await read_json(request)
        if problem:
            return problem
        if not isinstance(raw, dict):
            return error(422, "invalid_payload", "Expected {username, password}")
        username, password = raw.get("username"), raw.get("password")
        key = (client_ip(request), str(username).lower()[:64])
        now = time.monotonic()
        recent = [t for t in login_failures.get(key, ()) if now - t < LOGIN_WINDOW_S]
        if len(recent) >= LOGIN_LIMIT:
            return error(429, "too_many_attempts", "Too many failed logins; try again in a few minutes")
        user = users.verify_login(username, password)
        if user is None:
            login_failures[key] = recent + [now]
            if len(login_failures) > 10000:   # 오래된 기록을 정리해 메모리가 끝없이 늘지 않게
                for old in [k for k, times in login_failures.items() if now - times[-1] >= LOGIN_WINDOW_S]:
                    del login_failures[old]
            audit.info("login failed for %r from %s", str(username)[:64], key[0])
            return error(401, "invalid_credentials", "Wrong username or password")
        login_failures.pop(key, None)
        token = users.create_session(user["id"], request.headers.get("user-agent", ""))
        response = JSONResponse({"login_required": True, "user": me_view(user)}, headers={"Cache-Control": "no-store"})
        set_session_cookie(response, request, token)
        audit.info("login %s from %s", user["username"], key[0])
        return response

    @app.post("/api/v1/auth/logout")
    async def auth_logout(request: Request):
        if cross_site(request):
            return error(403, "cross_site_request", "Request from another site was rejected")
        if users is not None:
            users.delete_session(request.cookies.get(SESSION_COOKIE))
        response = JSONResponse({"logged_out": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.put("/api/v1/auth/password")
    async def auth_password(request: Request):
        if users is None:
            return login_disabled()
        user, denied = require_user(request, allow_password_change=True)
        if denied:
            return denied
        raw, problem = await read_json(request)
        if problem:
            return problem
        if not isinstance(raw, dict):
            return error(422, "invalid_payload", "Expected {current_password, new_password}")
        try:
            changed = users.change_own_password(user["id"], raw.get("current_password"), raw.get("new_password"),
                                                request.cookies.get(SESSION_COOKIE))
        except UserError as exc:
            return user_error(exc)
        audit.info("password changed by %s", user["username"])
        return {"login_required": True, "user": me_view(changed)}

    async def admin(request):
        """회원 관리 경로 공통: (사용자, None) 또는 (None, 오류)"""
        if users is None:
            return None, login_disabled()
        return require_user(request)

    @app.get("/api/v1/users")
    async def user_list(request: Request):
        user, denied = await admin(request)
        if denied:
            return denied
        return JSONResponse({"users": users.list()}, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/users")
    async def user_create(request: Request):
        user, denied = await admin(request)
        if denied:
            return denied
        raw, problem = await read_json(request)
        if problem:
            return problem
        if not isinstance(raw, dict) or set(raw) - {"username", "password", "display_name"}:
            return error(422, "invalid_payload", "Expected {username, password, display_name}")
        try:
            created = users.create(raw.get("username"), raw.get("password"), raw.get("display_name", ""), must_change=True)
        except UserError as exc:
            return user_error(exc)
        audit.info("user %s created by %s", created["username"], user["username"])
        return JSONResponse(created, status_code=201)

    @app.patch("/api/v1/users/{user_id}")
    async def user_update(user_id: int, request: Request):
        user, denied = await admin(request)
        if denied:
            return denied
        raw, problem = await read_json(request)
        if problem:
            return problem
        if not isinstance(raw, dict) or not raw or set(raw) - {"display_name", "active", "password"}:
            return error(422, "invalid_payload", "Expected some of {display_name, active, password}")
        try:
            updated = users.update(user_id, actor_id=user["id"], display_name=raw.get("display_name"),
                                   active=raw.get("active"), password=raw.get("password"))
        except UserError as exc:
            return user_error(exc)
        audit.info("user %s updated (%s) by %s", updated["username"], ", ".join(sorted(raw)), user["username"])
        return updated

    @app.delete("/api/v1/users/{user_id}")
    async def user_delete(user_id: int, request: Request):
        user, denied = await admin(request)
        if denied:
            return denied
        target = users.get(user_id)
        try:
            users.delete(user_id, actor_id=user["id"])
        except UserError as exc:
            return user_error(exc)
        audit.info("user %s deleted by %s", target["username"], user["username"])
        return Response(status_code=204)

    # WebSocket 입장표. 로그인한 화면이 이 경로에서 일회용 입장표를 받아 stream에 붙는다.
    # 입장표에는 발급받은 세션을 묶어 두고, 연결 중에도 그 세션이 끝나면(로그아웃·비활성화·만료) 연결을 끊는다
    stream_tickets = {}   # 입장표 → (만료 시각(monotonic), 세션 토큰 해시 또는 None)

    @app.post("/api/v1/stream-ticket")
    async def stream_ticket(request: Request):
        if (denied := require_user(request)[1]):
            return denied
        now = time.monotonic()
        for old_ticket in [t for t, (until, _) in stream_tickets.items() if until <= now]:
            del stream_tickets[old_ticket]
        if len(stream_tickets) >= STREAM_TICKET_LIMIT:
            return error(429, "too_many_tickets", "Too many unused stream tickets")
        ticket = secrets.token_urlsafe(24)
        session = request.cookies.get(SESSION_COOKIE)
        stream_tickets[ticket] = (now + STREAM_TICKET_TTL_S, token_hash(session) if users and session else None)
        return JSONResponse({"ticket": ticket}, headers={"Cache-Control": "no-store"})

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket, robot_id: str = "", ticket: str = ""):
        until, session = stream_tickets.pop(ticket, (0, None))
        if until <= time.monotonic() or (users and users.session_user(hashed=session) is None):
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

        async def watch_session():
            # 화면을 보고 있는 것도 활동으로 친다(touch). 세션이 끝나면 4401로 닫아 화면이 로그인으로 돌아가게 한다
            while True:
                await asyncio.sleep(SESSION_RECHECK_S)
                if users.session_user(hashed=session) is None:
                    with suppress(RuntimeError, WebSocketDisconnect):
                        await websocket.close(code=4401, reason="session_ended")
                    return

        tasks = [asyncio.create_task(send()), asyncio.create_task(watch_disconnect())]
        if users:
            tasks.append(asyncio.create_task(watch_session()))
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
