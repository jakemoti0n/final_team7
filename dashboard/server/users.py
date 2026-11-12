"""화면 로그인용 사용자 DB (SQLite). 계정은 모두 관리자(admin) 한 등급이다.

- 비밀번호는 표준 라이브러리 scrypt로 해시해 저장한다 (평문 저장 안 함, 계정마다 salt가 다름)
- 세션은 쿠키에 원본 토큰, DB에는 토큰의 sha256만 둔다 (DB가 새어도 세션을 쓸 수 없음)
- 서버는 프로세스 하나(--workers 1)라 연결 하나를 이벤트 루프에서만 쓴다. CLI가 같은 파일을 동시에 고쳐도 WAL로 안전

CLI (비밀번호 분실 복구·첫 계정 만들기):
    python -m server.users list
    python -m server.users add 아이디 [--name 이름] [--temporary]
    python -m server.users passwd 아이디 [--temporary]
    (컨테이너: docker compose exec dashboard python -m server.users passwd admin)
"""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,32}")
MIN_PASSWORD = 5          # 사용자 요청으로 완화. 대입 공격은 로그인 시도 제한(app.py)으로 늦춘다
MAX_PASSWORD = 256        # 아주 긴 입력으로 해시 계산을 오래 붙잡지 않게
MAX_DISPLAY_NAME = 64
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL COLLATE NOCASE,
  display_name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  must_change_password INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_login_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  last_seen REAL NOT NULL,
  user_agent TEXT);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
"""
SCHEMA_VERSION = 1


class UserError(Exception):
    """화면에 그대로 돌려줄 수 있는 오류 (HTTP 상태, 코드, 문구)"""
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def check_password(password, stored):
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# 없는 아이디로 로그인해도 해시 한 번만큼 시간이 걸리게 (아이디가 있는지 응답 시간으로 알 수 없게)
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def check_username(username):
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        raise UserError(422, "invalid_username", "아이디는 영문·숫자·_.- 3~32자여야 합니다")
    return username


def check_new_password(password):
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise UserError(422, "weak_password", f"비밀번호는 {MIN_PASSWORD}자 이상이어야 합니다")
    return password


def check_display_name(name):
    if not isinstance(name, str):
        raise UserError(422, "invalid_display_name", "이름은 문자열이어야 합니다")
    name = name.strip()
    if len(name) > MAX_DISPLAY_NAME or any(ord(c) < 32 for c in name):
        raise UserError(422, "invalid_display_name", f"이름은 {MAX_DISPLAY_NAME}자 이하여야 합니다")
    return name


def public(row):
    """화면에 보내는 사용자 정보 (해시 제외)"""
    if row is None:
        return None
    return dict(id=row["id"], username=row["username"], display_name=row["display_name"],
                active=bool(row["active"]), must_change_password=bool(row["must_change_password"]),
                created_at=row["created_at"], updated_at=row["updated_at"], last_login_at=row["last_login_at"])


class UserStore:
    def __init__(self, path, idle_s=12 * 3600, max_s=7 * 24 * 3600, clock=time.time):
        """path: SQLite 파일 (':memory:'는 시험용). idle_s: 마지막 활동 후 세션 유효 시간, max_s: 로그인 후 절대 만료"""
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.idle_s, self.max_s, self.clock = idle_s, max_s, clock
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"users db {path} is newer (version {version}) than this server ({SCHEMA_VERSION})")
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self):
        self.db.close()

    # ---- 사용자 ----

    def count(self, active_only=False):
        sql = "SELECT COUNT(*) FROM users" + (" WHERE active=1" if active_only else "")
        return self.db.execute(sql).fetchone()[0]

    def _row(self, user_id):
        return self.db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def _need(self, user_id):
        row = self._row(user_id)
        if row is None:
            raise UserError(404, "user_not_found", "사용자를 찾을 수 없습니다")
        return row

    def get(self, user_id):
        return public(self._row(user_id))

    def by_username(self, username):
        return public(self.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone())

    def list(self):
        return [public(r) for r in self.db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")]

    def create(self, username, password, display_name="", must_change=True):
        username = check_username(username)
        password = check_new_password(password)
        display_name = check_display_name(display_name)
        now = utc_now()
        try:
            cursor = self.db.execute(
                "INSERT INTO users(username, display_name, password_hash, must_change_password, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?)", (username, display_name, hash_password(password), int(must_change), now, now))
        except sqlite3.IntegrityError:
            raise UserError(409, "username_taken", "이미 있는 아이디입니다") from None
        return self.get(cursor.lastrowid)

    def update(self, user_id, actor_id=None, display_name=None, active=None, password=None):
        """관리자가 다른 사용자를 고친다. actor_id는 요청한 사람 (CLI는 None).
        비활성화·비밀번호 재설정이면 그 사용자의 세션을 모두 끊는다."""
        row = self._need(user_id)
        changes = {}
        if display_name is not None:
            changes["display_name"] = check_display_name(display_name)
        if active is not None:
            if not isinstance(active, bool):
                raise UserError(422, "invalid_payload", "active는 true/false여야 합니다")
            if not active and row["active"]:
                if user_id == actor_id:
                    raise UserError(409, "cannot_disable_self", "자기 계정은 비활성화할 수 없습니다")
                if self.count(active_only=True) <= 1:
                    raise UserError(409, "last_admin", "마지막 관리자 계정은 비활성화할 수 없습니다")
            changes["active"] = int(active)
        if password is not None:
            changes["password_hash"] = hash_password(check_new_password(password))
            changes["must_change_password"] = 1     # 재설정한 비밀번호는 임시. 본인이 첫 로그인에서 바꾼다
        if not changes:
            return public(row)
        changes["updated_at"] = utc_now()
        with self.db:
            self.db.execute("BEGIN")
            self.db.execute(f"UPDATE users SET {', '.join(f'{k}=?' for k in changes)} WHERE id=?",
                            (*changes.values(), user_id))
            if changes.get("active") == 0 or "password_hash" in changes:
                self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return self.get(user_id)

    def delete(self, user_id, actor_id=None):
        row = self._need(user_id)
        if user_id == actor_id:
            raise UserError(409, "cannot_delete_self", "자기 계정은 삭제할 수 없습니다")
        if row["active"] and self.count(active_only=True) <= 1:
            raise UserError(409, "last_admin", "마지막 관리자 계정은 삭제할 수 없습니다")
        self.db.execute("DELETE FROM users WHERE id=?", (user_id,))   # 세션은 ON DELETE CASCADE

    def set_password(self, user_id, password, must_change=False):
        """CLI 복구용: 비밀번호를 바로 바꾸고 그 사용자의 세션을 모두 끊는다"""
        self._need(user_id)
        password = check_new_password(password)
        with self.db:
            self.db.execute("BEGIN")
            self.db.execute("UPDATE users SET password_hash=?, must_change_password=?, updated_at=? WHERE id=?",
                            (hash_password(password), int(must_change), utc_now(), user_id))
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def change_own_password(self, user_id, current, new, keep_token):
        """본인이 비밀번호를 바꾼다. 지금 세션만 남기고 다른 기기의 세션은 끊는다"""
        row = self._need(user_id)
        if not isinstance(current, str) or not check_password(current, row["password_hash"]):
            raise UserError(403, "wrong_password", "현재 비밀번호가 맞지 않습니다")
        new = check_new_password(new)
        if new == current:
            raise UserError(422, "same_password", "새 비밀번호가 지금 비밀번호와 같습니다")
        with self.db:
            self.db.execute("BEGIN")
            self.db.execute("UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?",
                            (hash_password(new), utc_now(), user_id))
            self.db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, token_hash(keep_token)))
        return self.get(user_id)

    def verify_login(self, username, password):
        """맞으면 사용자, 아니면 None. 없는 아이디·비활성 계정·틀린 비밀번호를 구분하지 않는다"""
        row = None
        if isinstance(username, str) and USERNAME.fullmatch(username):
            row = self.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        password = password if isinstance(password, str) and len(password) <= MAX_PASSWORD else ""
        ok = check_password(password, row["password_hash"] if row else _DUMMY_HASH)
        if not (ok and row and row["active"]):
            return None
        self.db.execute("UPDATE users SET last_login_at=? WHERE id=?", (utc_now(), row["id"]))
        return self.get(row["id"])

    # ---- 세션 ----

    def create_session(self, user_id, user_agent=""):
        token = secrets.token_urlsafe(32)
        now = self.clock()
        self.db.execute("INSERT INTO sessions(token_hash, user_id, created_at, last_seen, user_agent) VALUES(?,?,?,?,?)",
                        (token_hash(token), user_id, now, now, (user_agent or "")[:200]))
        return token

    def session_user(self, token=None, hashed=None, touch=True):
        """유효한 세션의 사용자 또는 None. 만료된 세션은 지운다. touch면 마지막 활동 시각을 갱신"""
        if not token and not hashed:
            return None
        hashed = hashed or token_hash(token)
        now = self.clock()
        row = self.db.execute(
            "SELECT s.created_at AS s_created, s.last_seen AS s_seen, u.* FROM sessions s JOIN users u ON u.id=s.user_id"
            " WHERE s.token_hash=?", (hashed,)).fetchone()
        if row is None:
            return None
        if not row["active"] or now - row["s_seen"] > self.idle_s or now - row["s_created"] > self.max_s:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (hashed,))
            return None
        if touch and now - row["s_seen"] >= 60:   # 요청마다 쓰지 않게 1분에 한 번만
            self.db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, hashed))
        return public(row)

    def delete_session(self, token):
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))

    def purge_sessions(self):
        """오래된 세션 정리 (서버 시작 때)"""
        now = self.clock()
        self.db.execute("DELETE FROM sessions WHERE last_seen<? OR created_at<?", (now - self.idle_s, now - self.max_s))

    # ---- 첫 관리자 ----

    def bootstrap(self, environ=os.environ):
        """계정이 하나도 없으면 ADMIN_USERNAME/ADMIN_PASSWORD로 첫 관리자를 만든다 (첫 로그인 때 비밀번호 변경).
        계정이 있으면 두 값은 무시한다. 둘 다 없으면 아무도 로그인할 수 없으므로 서버를 띄우지 않는다."""
        username = environ.get("ADMIN_USERNAME", "").strip()
        password = environ.get("ADMIN_PASSWORD", "")
        if self.count():
            if password:
                logging.warning("ADMIN_PASSWORD is ignored because users already exist; remove it from .env")
            return None
        if not username or not password:
            raise RuntimeError("No dashboard users yet: set ADMIN_USERNAME and ADMIN_PASSWORD for the first start "
                               "(or run: python -m server.users add <username>)")
        try:
            user = self.create(username, password, must_change=True)
        except UserError as exc:
            raise RuntimeError(f"ADMIN_USERNAME/ADMIN_PASSWORD rejected: {exc.message}") from exc
        logging.warning("first admin created: %s (must change password on first login)", user["username"])
        return user


# ---- CLI ----

def default_db_path():
    """서버와 같은 설정 파일의 users_db. DASHBOARD_CONFIG → dashboard/config.json → dashboard/deploy/config.json"""
    root = Path(__file__).resolve().parents[1]
    candidates = [os.environ.get("DASHBOARD_CONFIG"), root / "config.json", root / "deploy" / "config.json"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            value = json.loads(Path(candidate).read_text()).get("users_db")
            if not value:
                raise SystemExit(f"{candidate} has no users_db; pass --db PATH")
            path = Path(value).expanduser()
            return path if path.is_absolute() else root.parent / path
    raise SystemExit("config not found; pass --db PATH")


def _ask_password():
    while True:
        first = getpass.getpass("새 비밀번호: ")
        if getpass.getpass("한 번 더: ") != first:
            print("두 비밀번호가 다릅니다. 다시 입력하세요.", file=sys.stderr)
            continue
        try:
            return check_new_password(first)
        except UserError as exc:
            print(exc.message, file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m server.users", description="관제 화면 사용자 관리 (서버가 켜져 있어도 됨)")
    parser.add_argument("--db", help="SQLite 파일 (기본: 설정 파일의 users_db)")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="사용자 목록")
    add = sub.add_parser("add", help="관리자 계정 추가")
    add.add_argument("username")
    add.add_argument("--name", default="", help="표시 이름")
    add.add_argument("--temporary", action="store_true", help="임시 비밀번호: 첫 로그인 때 바꾸게 함")
    passwd = sub.add_parser("passwd", help="비밀번호 다시 설정 (그 사용자의 로그인은 모두 끊김). 비활성 계정이면 다시 활성화")
    passwd.add_argument("username")
    passwd.add_argument("--temporary", action="store_true", help="임시 비밀번호: 첫 로그인 때 바꾸게 함")
    args = parser.parse_args(argv)

    store = UserStore(str(Path(args.db) if args.db else default_db_path()))
    try:
        if args.action == "list":
            for user in store.list():
                state = "활성" if user["active"] else "비활성"
                print(f"{user['username']}\t{user['display_name']}\t{state}\t마지막 로그인 {user['last_login_at'] or '-'}")
            return 0
        if args.action == "add":
            check_username(args.username)
            user = store.create(args.username, _ask_password(), args.name, must_change=args.temporary)
            print(f"추가함: {user['username']}")
            return 0
        user = store.by_username(args.username)
        if user is None:
            print(f"없는 아이디: {args.username}", file=sys.stderr)
            return 1
        store.set_password(user["id"], _ask_password(), must_change=args.temporary)
        if not user["active"]:
            store.update(user["id"], active=True)
        print(f"비밀번호를 바꿨습니다: {user['username']} (기존 로그인은 모두 끊김)")
        return 0
    except UserError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
