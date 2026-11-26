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
from .display import DisplayFolder, DisplayError
from .eco import EcoError, EcoState
from .waypoints import WaypointFile, WaypointError
from .guide import GuideFile, GuideError, MAX_BYTES as GUIDE_MAX_BYTES, MAX_IMAGE_BYTES, IMAGE_TYPES, area_at
from .models import CommandClaim, CommandRequest, CommandResult, Settings, Telemetry, uuid_string
from .state import Store, FINAL
from .users import UserError, UserStore, token_hash

ROOT = Path(__file__).resolve().parents[1]


def error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


async def read_json(request, limit=8192):
    """(본문, 오류 응답). 텔레메트리와 같은 규칙: JSON, 기본 8192바이트 이하 (약도 저장만 더 크게)."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        return None, error(415, "unsupported_media_type", "Expected application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            return None, error(413, "payload_too_large", f"Maximum request body is {limit} bytes")
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
VISITOR_POSITION_MAX_AGE_S = 60   # 방문자 화면: 이보다 오래된 위치는 보여 주지 않는다 (엉뚱한 곳으로 안내하지 않게)

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


def load_eco_token(settings, environ=os.environ):
    """분리수거 성공률(POST /api/v1/eco)의 토큰. 환경 변수 ECO_TOKEN → eco_token_file 순서.
    (켤지, 토큰) — 없으면 allow_no_robot_token일 때만 토큰 없이 받고, 아니면 받지 않는다(선택 기능이라 서버는 뜬다)."""
    token = environ.get("ECO_TOKEN", "").strip()
    if not token and settings.eco_token_file:
        path = Path(settings.eco_token_file).expanduser()
        path = path if path.is_absolute() else ROOT.parent / path
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"eco_token_file cannot be read: {path} ({exc})") from exc
        if not token:
            raise RuntimeError(f"eco_token_file is empty: {path}")
    if token:
        if len(token) < MIN_TOKEN_LENGTH or any(c.isspace() for c in token):
            raise RuntimeError(f"eco token must be at least {MIN_TOKEN_LENGTH} characters without spaces")
        if token == environ.get("ROBOT_TOKEN", "").strip():
            raise RuntimeError("ECO_TOKEN must differ from ROBOT_TOKEN")
        return True, token
    if settings.allow_no_robot_token:
        logging.warning("eco endpoint accepts requests without a token (allow_no_robot_token)")
        return True, None
    logging.info("eco endpoint is off: set ECO_TOKEN or eco_token_file to receive recycling results")
    return False, None


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


def create_app(settings=None, store=None, robot_token=None, users=None, eco_token=None):
    """settings를 주지 않으면 설정 파일을 읽고 로봇 토큰·성공률 토큰·사용자 DB도 설정대로 연다(운영 경로).
    settings를 직접 주면(시험·내장) robot_token·eco_token·users 인자를 그대로 쓴다. None이면 그 검사를 하지 않는다."""
    if settings is None:
        settings = Settings.model_validate_json(Path(os.environ.get("DASHBOARD_CONFIG", ROOT / "config.json")).read_text())
        robot_token = load_robot_token(settings)
        eco_enabled, eco_token = load_eco_token(settings)
        users = load_users(settings)
        owns_users = users is not None   # 직접 연 DB만 끌 때 닫는다 (시험이 넘긴 DB는 시험이 닫음)
    else:
        owns_users, eco_enabled = False, True
    expected = robot_token.encode() if robot_token else None
    eco_expected = eco_token.encode() if eco_token else None

    def unauthorized(request, token=None, what="robot"):
        """로봇용 경로 인증(token을 주면 그 토큰으로). 맞으면 None, 아니면 401 응답 (본문을 읽기 전에 검사)"""
        token = expected if what == "robot" else token
        if token is None:
            return None
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(given.strip().encode(), token):
            return None
        response = error(401, "unauthorized", f"Missing or invalid {what} token")
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
    # 분리수거 성공률 (장면 ⑤ 나무). 오래됨은 서버가 받은 시각으로 재므로 Store와 같은 시계를 쓴다
    eco = EcoState(settings, base_store.monotonic, base_store.utc)
    robots = {}           # robot_id → Robot. 넣은 순서 = 화면 목록 순서 (기본 로봇, 설정, 자동 등록 순)
    maps = {}             # (map_yaml, waypoints_yaml) → (메타, PNG, 자동 약도 SVG) 또는 None. 같은 파일은 한 번만 읽는다
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
            self.map_meta, self.map_png, self.map_sketch = load_map(map_yaml, waypoints_yaml)
            self.map_key = map_yaml if self.map_meta is not None else None   # 같은 지도인지 비교용
            self.map_yaml = map_yaml
            if self.map_meta is not None:
                # 지도 그림 주소에 로봇을 붙인다 (로봇마다 지도가 다를 수 있음)
                self.map_meta = {**self.map_meta, "image": f"/api/v1/map.png?robot_id={robot_id}",
                                 "sketch": f"/api/v1/map_sketch.svg?robot_id={robot_id}" if self.map_sketch else None}
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
            return None, None, None
        key = (map_yaml, waypoints_yaml)
        if key not in maps:
            try:
                maps[key] = mapdata.load(map_yaml, waypoints_yaml, base=ROOT.parent)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logging.error("map not loaded: %s", exc)
                maps[key] = None
        return maps[key] or (None, None, None)

    def register(robot_id, robot_store=None):
        robots[robot_id] = Robot(robot_id, robot_store or Store(
            settings, base_store.monotonic, base_store.utc, robot_id=robot_id))
        return robots[robot_id]

    register(settings.robot_id, base_store)
    for robot_id in settings.robots:
        if robot_id not in robots:
            register(robot_id)

    # 방문자 안내 약도: 기본 로봇의 지도 좌표. 지도가 없으면 그릴 기준이 없으므로 쓰지 않는다
    home_robot = robots[settings.robot_id]
    guide_file, guide_lock = None, asyncio.Lock()
    if settings.guide_yaml and home_robot.map_meta is not None:
        guide_path = Path(settings.guide_yaml).expanduser()
        guide_path = guide_path if guide_path.is_absolute() else ROOT.parent / guide_path
        guide_file = GuideFile(guide_path, home_robot.map_meta, Path(home_robot.map_yaml).name)

    # 로봇 하단 디스플레이 내용 (display.json + 팜플렛). 지도와 상관없다
    display_folder = None
    if settings.display_dir:
        display_path = Path(settings.display_dir).expanduser()
        display_folder = DisplayFolder(display_path if display_path.is_absolute() else ROOT.parent / display_path)

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

    def guide_missing():
        return error(404, "guide_not_configured", "Set guide_yaml and map_yaml in the server config")

    @app.get("/api/v1/guide")
    async def get_guide(request: Request):
        if (denied := require_user(request)[1]):
            return denied
        if guide_file is None:
            return guide_missing()
        try:
            return guide_file.document()
        except (OSError, GuideError) as exc:
            logging.error("guide not loaded: %s", exc)
            return error(503, "guide_unavailable", f"Guide file cannot be read: {exc}")

    @app.put("/api/v1/guide")
    async def save_guide(request: Request):
        user, denied = require_user(request)
        if denied:
            return denied
        if guide_file is None:
            return guide_missing()
        raw, problem = await read_json(request, GUIDE_MAX_BYTES)
        if problem:
            return problem
        async with guide_lock:   # 로봇 동작과 무관하므로 순찰 중에도 저장한다
            try:
                document = guide_file.save(raw)
            except GuideError as exc:
                return error(409 if exc.code == "revision_conflict" else 422, exc.code, str(exc))
            except OSError as exc:
                logging.error("guide not saved: %s", exc)
                return error(503, "guide_unavailable", "Guide file cannot be saved")
        guide = document["guide"]
        audit.info("guide saved by %s (%d areas, %d markers)", who(user), len(guide["areas"]), len(guide["markers"]))
        return document

    @app.put("/api/v1/guide/image")
    async def upload_guide_image(request: Request):
        """약도 그림 올리기 (본문은 그림 그대로). 약도를 저장해야 쓰인다"""
        user, denied = require_user(request)
        if denied:
            return denied
        if guide_file is None:
            return guide_missing()
        if request.headers.get("content-type", "").split(";")[0].strip().lower() not in IMAGE_TYPES.values():
            return error(415, "unsupported_media_type", "Upload a PNG, JPEG or WebP image")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_IMAGE_BYTES:
                return error(413, "image_too_large", f"Image must be at most {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
            body.extend(chunk)
        try:
            info = guide_file.save_image(bytes(body))
        except GuideError as exc:
            return error(413 if exc.code == "image_too_large" else 422, exc.code, str(exc))
        except OSError as exc:
            logging.error("guide image not saved: %s", exc)
            return error(503, "guide_unavailable", "Image cannot be saved")
        audit.info("guide image %s uploaded by %s", info["file"], who(user))
        return JSONResponse(info, status_code=201)

    def guide_image_response(name):
        found = guide_file.image(name) if guide_file is not None else None
        if found is None:
            return error(404, "image_not_found", "No such guide image")
        data, media = found
        # 이름이 내용의 해시라 바뀌지 않는다. 그림을 문서로 열어도 스크립트가 돌지 않게 막는다
        return Response(data, media_type=media, headers={
            "Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'"})

    @app.get("/api/v1/guide/image/{name}")
    async def guide_image(request: Request, name: str):
        if (denied := require_user(request)[1]):
            return denied
        if guide_file is None:
            return guide_missing()
        return guide_image_response(name)

    @app.get("/api/v1/guide/file")
    async def download_guide(request: Request):
        """저장된 약도 파일 그대로 (클라우드에서 고친 약도를 저장소로 가져갈 때)"""
        if (denied := require_user(request)[1]):
            return denied
        if guide_file is None:
            return guide_missing()
        try:
            body = guide_file.raw()
        except OSError as exc:
            logging.error("guide not loaded: %s", exc)
            return error(503, "guide_unavailable", "Guide file cannot be read")
        if body is None:
            return error(404, "guide_not_saved", "The guide has not been saved yet")
        return Response(body, media_type="application/yaml", headers={
            "Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="{guide_file.path.name}"'})

    @app.get("/api/v1/map.png")
    async def map_image(request: Request, robot_id: str = ""):
        if (denied := require_user(request)[1]):
            return denied
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.map_png is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return Response(robot.map_png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/map_sketch.svg")
    async def map_sketch(request: Request, robot_id: str = ""):
        """서버가 지도를 읽을 때 만든 자동 약도. 원본 지도와 영역·크기가 같다"""
        if (denied := require_user(request)[1]):
            return denied
        if (robot := find(robot_id)) is None:
            return unknown_robot()
        if robot.map_sketch is None:
            return error(404, "map_sketch_unavailable", "Map sketch is not available; use the original map")
        # 서버가 만든 SVG지만, 주소로 직접 열어도 스크립트·외부 자원이 돌지 않게 막는다
        return Response(robot.map_sketch, media_type="image/svg+xml",
                        headers={"Cache-Control": "no-cache", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

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

    # ---- 방문자 안내 (로그인 없음, 읽기 전용). visitor_enabled일 때만 열린다 ----

    def visitor_closed():
        return error(404, "visitor_disabled", "Visitor page is not enabled")

    def visitor_robot(robot, home, areas):
        """방문자에게 보여도 되는 것만: 이름, 쉬운 상태, 대략 위치, 약도 구역 이름, 순찰 진행, 움직이는 중.
        waypoint 이름·좌표는 내보내지 않는다(다음 지점도 구역 이름으로만). areas는 방문자에게 보이는 약도의 구역 (없으면 [])
        snapshot()을 부르지 않아 알림·revision을 건드리지 않는다"""
        connection, _ = robot.store.connection()
        patrol = (robot.store.payload or {}).get("patrol") or {}
        patrol_state = patrol.get("state")
        if connection == "disconnected":
            status = "offline"
        elif connection != "connected":
            status = "checking"   # 처음 확인 중이거나 수신 지연: 지금 상태를 모른다
        elif patrol_state in ("pausing", "paused"):
            status = "paused"
        elif robot.store.patrol_running():
            status = "patrolling"
        else:
            status = "idle"
        position = area = None
        # 약도는 기본 로봇의 지도 좌표라서, 지도가 다른 로봇은 위치·구역을 낼 수 없다
        same_map = home.map_key is not None and robot.map_key == home.map_key
        pose = robot.store.pose_view() if same_map else None
        if pose is not None and (pose["age_s"] is None or pose["age_s"] <= VISITOR_POSITION_MAX_AGE_S):
            position = dict(x=round(pose["x"] * 2) / 2, y=round(pose["y"] * 2) / 2, stale=pose["stale"],
                            age_s=None if pose["age_s"] is None else round(pose["age_s"]))
            # 구역은 반올림 전 위치로 (경계 근처에서 0.5 m 반올림 때문에 옆 구역으로 튀지 않게)
            area = area_at(areas, pose["x"], pose["y"])
        # 순찰 진행: waypoint_index는 다음 목표 (0부터, 끝나면 waypoint_count와 같음)
        progress = next_area = None
        index, count = patrol.get("waypoint_index"), patrol.get("waypoint_count")
        if (status in ("patrolling", "paused") and patrol_state in ("patrolling", "pausing", "paused")
                and index is not None and count and index < count):
            progress = dict(done=index, total=count)
            targets = robot.waypoint_file.targets() if same_map and robot.waypoint_file is not None else None
            # 서버 파일이 로봇이 도는 경로와 같을 때만 (순찰 시작 뒤 편집했으면 번호가 어긋날 수 있다)
            if targets is not None and len(targets) == count and targets[index][0] == patrol.get("waypoint_name"):
                next_area = area_at(areas, targets[index][1], targets[index][2])
        # 로봇 근처에 "지나갑니다"를 띄울 근거: 순찰 중이면서 앞으로 가는 중. 속도 값이 오래됐으면 None(모름)
        moving = robot.store.moving() if status == "patrolling" else False
        return dict(robot_id=robot.id, status=status, position=position, area=area,
                    next_area=next_area, progress=progress, moving=moving)

    def display_revision():
        if display_folder is None:
            return None
        try:
            return display_folder.view()["revision"]
        except DisplayError:
            return None

    @app.get("/api/v1/visitor/state")
    async def visitor_state():
        if not settings.visitor_enabled:
            return visitor_closed()
        home = find("")
        meta = home.map_meta
        public_guide = guide_file.public() if guide_file is not None else None
        areas = public_guide["areas"] if public_guide else []
        items = [visitor_robot(robot, home, areas) for robot in robots.values()]
        body = dict(server_utc=base_store.utc(), robots=items,
                    operating=sum(item["status"] in ("patrolling", "paused", "idle") for item in items),
                    map=None if meta is None else dict(resolution=meta["resolution"], origin=meta["origin"],
                                                       width=meta["width"], height=meta["height"],
                                                       image="/api/v1/visitor/map.png",
                                                       sketch="/api/v1/visitor/map_sketch.svg" if home.map_sketch else None),
                    # 안내 약도는 바뀔 때만 따로 받게 판만 알려 준다 (없으면 null → 자동 약도가 메인)
                    guide=public_guide["revision"] if public_guide else None,
                    # 하단 디스플레이 내용(일정·팜플렛)도 같은 방식. 폴더가 없거나 읽을 수 없으면 null
                    display=display_revision(),
                    # 분리수거 성공률 판정 (장면 ⑤). initial이면 숫자 없음. 보낸 곳·시각은 내보내지 않는다
                    eco=eco.view())
        return JSONResponse(body, headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/visitor/map.png")
    async def visitor_map():
        if not settings.visitor_enabled:
            return visitor_closed()
        home = find("")
        if home.map_png is None:
            return error(404, "map_not_configured", "Set map_yaml in the server config")
        return Response(home.map_png, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/visitor/map_sketch.svg")
    async def visitor_map_sketch():
        if not settings.visitor_enabled:
            return visitor_closed()
        home = find("")
        if home.map_sketch is None:
            return error(404, "map_sketch_unavailable", "Map sketch is not available")
        return Response(home.map_sketch, media_type="image/svg+xml",
                        headers={"Cache-Control": "no-cache", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

    @app.get("/api/v1/visitor/guide")
    async def visitor_guide():
        """방문자 안내 약도. 구역·이름·종류·그림만 (기준점·지도 이름·순찰 지점 없음)"""
        if not settings.visitor_enabled:
            return visitor_closed()
        view = guide_file.public() if guide_file is not None else None
        if view is None:
            return error(404, "guide_not_available", "No visitor guide has been drawn")
        image = view["image"]
        body = {**view, "image": None if image is None else {**image, "url": f"/api/v1/visitor/guide/image/{image['file']}"}}
        return JSONResponse(body, headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/visitor/guide/image/{name}")
    async def visitor_guide_image(name: str):
        # 지금 약도가 쓰는 그림 하나만 공개한다 (올렸지만 저장하지 않은 그림은 보이지 않게)
        if not settings.visitor_enabled:
            return visitor_closed()
        view = guide_file.public() if guide_file is not None else None
        if view is None or view["image"] is None or view["image"]["file"] != name:
            return error(404, "image_not_found", "No such guide image")
        return guide_image_response(name)

    # ---- 로봇 하단 디스플레이 (/display). 방문자 화면과 같이 로그인 없이 읽기만, visitor_enabled일 때만 ----

    @app.get("/api/v1/display/content")
    async def display_content():
        """일정·문구·팜플렛 목록·장면 길이. 바뀌면 visitor/state의 display 값이 바뀐다"""
        if not settings.visitor_enabled:
            return visitor_closed()
        if display_folder is None:
            return error(404, "display_not_configured", "Set display_dir in the server config")
        try:
            view = display_folder.view()
        except DisplayError as exc:
            # 운영자가 고칠 내용은 로그에 (서버 경로를 방문자에게 보이지 않게)
            return error(503, "display_unavailable", "Display content is missing or invalid; see the server log"
                         if exc.code == "invalid_display" else "Display content has not been set up")
        return JSONResponse(view, headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/display/slides/{name}")
    async def display_slide(name: str):
        # display.json에 적은 그림만 (폴더에 있어도 목록에 없으면 내주지 않는다)
        if not settings.visitor_enabled:
            return visitor_closed()
        found = display_folder.slide(name) if display_folder is not None else None
        if found is None:
            return error(404, "slide_not_found", "No such slide")
        data, media = found
        # 주소에 내용 해시(?v=)가 붙으므로 오래 캐시해도 된다. 그림을 문서로 열어도 스크립트가 돌지 않게
        return Response(data, media_type=media, headers={
            "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'"})

    @app.get("/api/v1/display/sound/{name}")
    async def display_sound(name: str):
        # display.json의 sound에 적은 파일만 (「LIMBO가 지나갑니다」 때 한 번)
        if not settings.visitor_enabled:
            return visitor_closed()
        found = display_folder.sound(name) if display_folder is not None else None
        if found is None:
            return error(404, "sound_not_found", "No such sound")
        data, media = found
        return Response(data, media_type=media, headers={
            "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'"})

    # ---- 분리수거 성공률 (Raspberry Pi → 서버). 로봇 토큰과 다른 성공률 전용 토큰 ----

    @app.post("/api/v1/eco")
    async def receive_eco(request: Request):
        """Pi가 1분쯤마다(값이 그대로여도) 보낸다. 형식이 틀리면 422이고 마지막 정상 값은 그대로"""
        if not eco_enabled:
            return error(404, "eco_not_configured", "Set ECO_TOKEN or eco_token_file in the server config")
        if denied := unauthorized(request, eco_expected, "eco"):
            return denied
        raw, problem = await read_json(request, limit=4096)
        if problem:
            return problem
        try:
            view = eco.accept(raw)
        except EcoError as exc:
            return error(422, "invalid_payload", str(exc))
        return {"accepted": True, "eco": view}

    dist = ROOT / "ui" / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    def index_html():
        if not (dist / "index.html").exists():
            return error(503, "server_error", "Build dashboard/ui first; see README")
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/")
    @app.get("/demo")
    async def ui():
        return index_html()

    @app.get("/display")   # 로봇 하단 디스플레이(키오스크). 방문자 안내와 같은 조건으로 연다
    @app.get("/visitor")
    async def visitor_ui(demo: str | None = None):
        # 데모(?demo)는 서버 데이터를 쓰지 않으므로 꺼져 있어도 연다
        if not settings.visitor_enabled and demo is None:
            return visitor_closed()
        return index_html()

    return app


app = create_app()
