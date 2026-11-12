"""화면 로그인·회원 관리 (SQLite 사용자 DB, 세션 쿠키). 계정은 모두 관리자 한 등급."""
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server.app as app_module
from server import users as users_module
from server.app import create_app, load_users
from server.models import Settings
from server.users import UserError, UserStore, check_password, hash_password
from tools.sender import sample

PASSWORD = 'first-pass'


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def store():
    store = UserStore(':memory:')
    store.create('admin', PASSWORD, 'Admin', must_change=False)
    yield store
    store.close()


@pytest.fixture
def client(store):
    with TestClient(create_app(Settings(), users=store)) as client:
        yield client


def login(client, username='admin', password=PASSWORD):
    return client.post('/api/v1/auth/login', json={'username': username, 'password': password})


# ---- 저장소 ----

def test_password_hash_is_salted_and_never_plain():
    first, second = hash_password('secret'), hash_password('secret')
    assert first != second and 'secret' not in first and first.startswith('scrypt$')
    assert check_password('secret', first) and not check_password('Secret', first)
    assert not check_password('secret', 'garbage') and not check_password('secret', 'md5$x$y$z$a$b')


def test_create_rules(store):
    with pytest.raises(UserError, match='5자 이상'):
        store.create('short', '1234')
    assert store.create('five', '12345')['must_change_password'] is True
    with pytest.raises(UserError) as exc:
        store.create('ADMIN', 'whatever')   # 대소문자만 다른 아이디도 같은 아이디
    assert exc.value.code == 'username_taken'
    for bad in ('ab', 'has space', 'x' * 33, '한글아이디', 7):
        with pytest.raises(UserError) as exc:
            store.create(bad, 'whatever')
        assert exc.value.code == 'invalid_username'
    assert 'password_hash' not in store.list()[0]


def test_last_admin_and_self_are_protected(store):
    admin = store.by_username('admin')
    for call in (lambda: store.delete(admin['id']), lambda: store.update(admin['id'], active=False)):
        with pytest.raises(UserError) as exc:
            call()
        assert exc.value.code == 'last_admin'
    other = store.create('other', 'other-pass')
    with pytest.raises(UserError, match='자기 계정'):
        store.delete(admin['id'], actor_id=admin['id'])
    with pytest.raises(UserError, match='자기 계정'):
        store.update(admin['id'], actor_id=admin['id'], active=False)
    store.update(admin['id'], actor_id=other['id'], active=False)   # 다른 관리자는 할 수 있다
    with pytest.raises(UserError) as exc:   # 이제 other가 마지막 활성 관리자
        store.delete(other['id'], actor_id=None)
    assert exc.value.code == 'last_admin'
    store.delete(admin['id'], actor_id=other['id'])                  # 비활성 계정 삭제는 언제나 가능
    assert [u['username'] for u in store.list()] == ['other']


def test_sessions_end_on_disable_reset_delete_and_expiry():
    clock = Clock()
    store = UserStore(':memory:', idle_s=100, max_s=1000, clock=clock)
    admin = store.create('admin', PASSWORD, must_change=False)
    other = store.create('other', 'other-pass', must_change=False)
    token = store.create_session(other['id'])
    assert store.session_user(token)['username'] == 'other'
    store.update(other['id'], actor_id=admin['id'], display_name='이름만')   # 이름 변경은 세션 유지
    assert store.session_user(token)
    store.update(other['id'], actor_id=admin['id'], password='reset-pass')
    assert store.session_user(token) is None
    assert store.get(other['id'])['must_change_password'] is True
    token = store.create_session(other['id'])
    store.update(other['id'], actor_id=admin['id'], active=False)
    assert store.session_user(token) is None and store.verify_login('other', 'reset-pass') is None
    # 쉬는 시간·절대 만료
    token = store.create_session(admin['id'])
    clock.now += 99
    assert store.session_user(token)        # 활동하면 쉬는 시간이 다시 시작
    clock.now += 99
    assert store.session_user(token)
    clock.now += 101
    assert store.session_user(token) is None
    token = store.create_session(admin['id'])
    for _ in range(11):
        clock.now += 95
        alive = store.session_user(token)
    assert alive is None                     # 계속 활동해도 1000초 뒤에는 다시 로그인
    token = store.create_session(admin['id'])
    store.delete(other['id'], actor_id=admin['id'])
    assert store.session_user(token)


def test_change_own_password_keeps_only_this_session(store):
    admin = store.by_username('admin')
    here, there = store.create_session(admin['id']), store.create_session(admin['id'])
    with pytest.raises(UserError) as exc:
        store.change_own_password(admin['id'], 'wrong', 'new-pass', here)
    assert exc.value.code == 'wrong_password'
    with pytest.raises(UserError) as exc:
        store.change_own_password(admin['id'], PASSWORD, PASSWORD, here)
    assert exc.value.code == 'same_password'
    store.change_own_password(admin['id'], PASSWORD, 'new-pass', here)
    assert store.session_user(here) and store.session_user(there) is None
    assert store.verify_login('admin', 'new-pass') and not store.verify_login('admin', PASSWORD)


def test_bootstrap_and_file_persistence(tmp_path):
    path = str(tmp_path / 'sub' / 'users.db')
    with pytest.raises(RuntimeError, match='ADMIN_USERNAME'):
        UserStore(path).bootstrap({})
    with pytest.raises(RuntimeError, match='rejected'):
        UserStore(path).bootstrap({'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD': '123'})
    first = UserStore(path)
    assert first.bootstrap({'ADMIN_USERNAME': 'boss', 'ADMIN_PASSWORD': 'boss-pass'})['must_change_password']
    first.close()
    again = UserStore(path)                 # 다시 열어도 남아 있고, 환경 변수는 무시
    assert again.bootstrap({'ADMIN_USERNAME': 'x', 'ADMIN_PASSWORD': 'other-pass'}) is None
    assert [u['username'] for u in again.list()] == ['boss'] and again.verify_login('boss', 'boss-pass')


def test_load_users_from_settings(tmp_path):
    with pytest.raises(RuntimeError, match='Set users_db'):
        load_users(Settings(), {})
    assert load_users(Settings(allow_no_login=True), {}) is None
    users = load_users(Settings(users_db=str(tmp_path / 'users.db')), {'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD': 'abcde'})
    assert users.verify_login('admin', 'abcde')


def test_cli_add_passwd_list(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / 'users.db')
    answers = iter(['cli-pass', 'cli-pass', 'new-pass', 'typo', 'new-pass', 'new-pass'])
    monkeypatch.setattr(users_module.getpass, 'getpass', lambda prompt='': next(answers))
    assert users_module.main(['--db', db, 'add', 'cli', '--name', '씨엘아이']) == 0
    store = UserStore(db)
    token = store.create_session(store.by_username('cli')['id'])
    assert users_module.main(['--db', db, 'passwd', 'cli']) == 0   # 처음 두 입력이 달라 한 번 더 묻는다
    assert store.session_user(token) is None and store.verify_login('cli', 'new-pass')
    assert not store.by_username('cli')['must_change_password']
    assert users_module.main(['--db', db, 'passwd', 'nobody']) == 1
    assert users_module.main(['--db', db, 'list']) == 0
    assert 'cli\t씨엘아이\t활성' in capsys.readouterr().out


# ---- API ----

BROWSER_PATHS = [
    ('get', '/api/v1/state'), ('get', '/api/v1/robots'), ('get', '/api/v1/map'), ('get', '/api/v1/map.png'),
    ('get', '/api/v1/waypoints'), ('put', '/api/v1/waypoints'), ('post', '/api/v1/commands'),
    ('post', '/api/v1/stream-ticket'), ('get', '/api/v1/users'), ('post', '/api/v1/users'),
    ('patch', '/api/v1/users/1'), ('delete', '/api/v1/users/1'), ('put', '/api/v1/auth/password'),
    ('get', '/api/v1/auth/me'),
]


@pytest.mark.parametrize('method,path', BROWSER_PATHS)
def test_browser_paths_need_login(client, method, path):
    kwargs = {'json': {}} if method in ('post', 'put', 'patch') else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'login_required'
    client.cookies.set('limbo_session', 'made-up-token')
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_login_cookie_me_logout(client):
    assert login(client, password='wrong').json()['error']['code'] == 'invalid_credentials'
    assert login(client, username='nobody').status_code == 401
    response = login(client)
    assert response.status_code == 200 and response.json()['user']['username'] == 'admin'
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/' in cookie
    assert 'secure' not in cookie            # 로컬 http 시험에서는 Secure 없이
    assert client.get('/api/v1/state').status_code == 200
    assert client.get('/api/v1/auth/me').json() == {'login_required': True, 'user': {
        'id': 1, 'username': 'admin', 'display_name': 'Admin', 'must_change_password': False}}
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/state').status_code == 401


def test_cookie_is_secure_behind_https_proxy(client):
    response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': PASSWORD},
                           headers={'X-Forwarded-Proto': 'https'})
    assert 'secure' in response.headers['set-cookie'].lower()


def test_first_login_must_change_password(store, client):
    store.create('newbie', 'temp-pass')
    assert login(client, 'newbie', 'temp-pass').json()['user']['must_change_password'] is True
    response = client.get('/api/v1/state')
    assert response.status_code == 403 and response.json()['error']['code'] == 'password_change_required'
    assert client.post('/api/v1/stream-ticket').status_code == 403
    assert client.get('/api/v1/auth/me').status_code == 200
    bad = client.put('/api/v1/auth/password', json={'current_password': 'temp-pass', 'new_password': '1234'})
    assert bad.json()['error']['code'] == 'weak_password'
    changed = client.put('/api/v1/auth/password', json={'current_password': 'temp-pass', 'new_password': 'mine-now'})
    assert changed.json()['user']['must_change_password'] is False
    assert client.get('/api/v1/state').status_code == 200   # 지금 세션은 그대로


def test_cross_site_requests_are_rejected(client):
    evil = {'Origin': 'https://evil.example'}
    assert client.post('/api/v1/auth/login', json={'username': 'admin', 'password': PASSWORD}, headers=evil).status_code == 403
    assert login(client).status_code == 200
    for method, path in [('post', '/api/v1/commands'), ('put', '/api/v1/waypoints'), ('post', '/api/v1/users'),
                         ('delete', '/api/v1/users/1'), ('post', '/api/v1/auth/logout')]:
        kwargs = {'json': {}} if method != 'delete' else {}
        response = getattr(client, method)(path, headers=evil, **kwargs)
        assert response.status_code == 403 and response.json()['error']['code'] == 'cross_site_request'
    assert client.get('/api/v1/state', headers=evil).status_code == 200   # 읽기는 브라우저 CORS가 막는다
    same = client.post('/api/v1/users', json={'username': 'ok-user', 'password': 'pass-1'}, headers={'Origin': 'http://testserver'})
    assert same.status_code == 201


def test_login_attempts_are_limited(client):
    for _ in range(10):
        assert login(client, password='wrong').status_code == 401
    assert login(client).status_code == 429                 # 맞는 비밀번호도 잠시 막힌다
    other = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': PASSWORD},
                        headers={'X-Forwarded-For': '10.0.0.9'})
    assert other.status_code == 200                          # 다른 IP는 영향 없음


def test_user_management_api(store, client):
    login(client)
    created = client.post('/api/v1/users', json={'username': 'kim', 'password': 'kim-temp', 'display_name': '김'})
    assert created.status_code == 201
    kim = created.json()
    assert kim['must_change_password'] is True and 'password_hash' not in kim
    assert client.post('/api/v1/users', json={'username': 'KIM', 'password': 'kim-temp'}).status_code == 409
    assert client.post('/api/v1/users', json={'username': 'lee', 'password': 'x', 'role': 'admin'}).status_code == 422
    assert [u['username'] for u in client.get('/api/v1/users').json()['users']] == ['admin', 'kim']

    other = TestClient(client.app)                    # kim이 다른 기기에서 로그인해 있다
    login(other, 'kim', 'kim-temp')
    assert other.get('/api/v1/auth/me').status_code == 200
    assert client.patch(f"/api/v1/users/{kim['id']}", json={'active': False}).json()['active'] is False
    assert other.get('/api/v1/auth/me').status_code == 401   # 비활성화하면 바로 끊긴다
    assert login(other, 'kim', 'kim-temp').status_code == 401
    assert client.patch(f"/api/v1/users/{kim['id']}", json={'active': True, 'password': 'kim-new1'}).status_code == 200
    assert login(other, 'kim', 'kim-new1').json()['user']['must_change_password'] is True

    me = store.by_username('admin')['id']
    assert client.patch(f'/api/v1/users/{me}', json={'active': False}).json()['error']['code'] == 'cannot_disable_self'
    assert client.delete(f'/api/v1/users/{me}').json()['error']['code'] == 'cannot_delete_self'
    assert client.patch(f'/api/v1/users/{me}', json={'role': 'viewer'}).status_code == 422
    assert client.patch(f'/api/v1/users/{me}', json={'active': 'no'}).status_code == 422
    assert client.patch('/api/v1/users/999', json={'display_name': 'x'}).status_code == 404
    assert client.delete('/api/v1/users/999').status_code == 404
    assert client.delete(f"/api/v1/users/{kim['id']}").status_code == 204
    assert other.get('/api/v1/auth/me').status_code == 401


def test_commands_record_who_issued_them(client):
    login(client)
    assert client.post('/api/v1/telemetry', json=sample(str(uuid.uuid4()))).json()['accepted']
    response = client.post('/api/v1/commands', json={'command': 'pause'})
    assert response.status_code == 202 and response.json()['issued_by'] == 'admin'
    assert client.get('/api/v1/state').json()['command']['issued_by'] == 'admin'


def test_stream_needs_a_ticket_from_a_live_session(client, monkeypatch):
    monkeypatch.setattr(app_module, 'SESSION_RECHECK_S', 0.05)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/api/v1/stream') as ws:
            ws.receive_json()
    login(client)
    stale = client.post('/api/v1/stream-ticket').json()['ticket']
    ticket = client.post('/api/v1/stream-ticket').json()['ticket']
    with client.websocket_connect(f'/api/v1/stream?ticket={ticket}') as ws:
        assert ws.receive_json()['robot_id'] == 'LIMBO-01'
        client.post('/api/v1/auth/logout')
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(50):
                ws.receive_json()
        assert closed.value.code == 4401            # 로그아웃하면 열려 있던 실시간 연결도 끊긴다
    with pytest.raises(WebSocketDisconnect):        # 로그아웃 전에 받은 입장표도 못 쓴다
        with client.websocket_connect(f'/api/v1/stream?ticket={stale}') as ws:
            ws.receive_json()


def test_server_without_login_keeps_screen_open():
    with TestClient(create_app(Settings())) as client:
        assert client.get('/api/v1/auth/me').json() == {'login_required': False, 'user': None}
        assert client.get('/api/v1/state').status_code == 200
        assert client.get('/api/v1/users').json()['error']['code'] == 'login_disabled'
        assert client.post('/api/v1/auth/login', json={'username': 'a', 'password': 'b'}).status_code == 404


def test_config_file_path_requires_users_db(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    monkeypatch.setenv('DASHBOARD_CONFIG', str(config))
    monkeypatch.setenv('ROBOT_TOKEN', 'robot-token-0123456789abcdef')
    monkeypatch.delenv('ADMIN_USERNAME', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    config.write_text('{}')
    with pytest.raises(RuntimeError, match='Set users_db'):
        create_app()
    config.write_text(f'{{"users_db": "{tmp_path / "users.db"}"}}')
    with pytest.raises(RuntimeError, match='ADMIN_USERNAME'):
        create_app()
    monkeypatch.setenv('ADMIN_USERNAME', 'admin')
    monkeypatch.setenv('ADMIN_PASSWORD', 'first')
    with TestClient(create_app()) as client:
        assert client.get('/api/v1/state').status_code == 401
        assert login(client, 'admin', 'first').json()['user']['must_change_password'] is True
