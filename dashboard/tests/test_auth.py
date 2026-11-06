"""로봇용 경로의 공유 토큰 인증 (Authorization: Bearer). 브라우저용 경로는 앞단 Caddy basic auth가 맡는다."""
import uuid

import pytest
from fastapi.testclient import TestClient

from server.app import create_app, load_robot_token
from server.models import Settings
from tools.sender import sample

TOKEN = 'robot-token-0123456789abcdef'
SESSION = str(uuid.uuid4())
ROBOT_PATHS = [
    ('post', '/api/v1/telemetry'),
    ('get', f'/api/v1/commands/next?robot_id=LIMBO-01&bridge_session_id={SESSION}&wait_s=0'),
    ('post', f'/api/v1/commands/{SESSION}/claim'),
    ('post', f'/api/v1/commands/{SESSION}/result'),
]


@pytest.fixture
def client():
    with TestClient(create_app(Settings(), robot_token=TOKEN)) as client:
        yield client


@pytest.mark.parametrize('method,path', ROBOT_PATHS)
@pytest.mark.parametrize('header', [None, 'Bearer wrong-token-0123456789', f'Basic {TOKEN}', 'Bearer', f'Bearer {TOKEN}x'])
def test_robot_paths_reject_missing_or_wrong_token(client, method, path, header):
    headers = {'Authorization': header} if header else {}
    response = getattr(client, method)(path, headers=headers, **({'json': {}} if method == 'post' else {}))
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'unauthorized'
    assert response.headers['www-authenticate'] == 'Bearer'


def test_correct_token_reaches_the_handler(client):
    auth = {'Authorization': f'Bearer {TOKEN}'}
    assert client.post('/api/v1/telemetry', json=sample(SESSION), headers=auth).json()['accepted']
    assert client.post('/api/v1/telemetry', json=sample(SESSION, 2), headers={'authorization': f'bearer {TOKEN}'}).json()['accepted']
    assert client.get(ROBOT_PATHS[1][1], headers=auth).status_code == 204
    assert client.post(ROBOT_PATHS[2][1], json={}, headers=auth).status_code == 422   # 인증 뒤 본문 검사


def test_browser_paths_do_not_need_the_robot_token(client):
    assert client.get('/api/v1/state').status_code == 200
    assert client.get('/healthz').status_code == 200
    assert client.post('/api/v1/commands', json={'command': 'pause'}).json()['error']['code'] == 'bridge_not_connected'


def test_no_token_configured_keeps_robot_paths_open():
    with TestClient(create_app(Settings())) as client:
        assert client.post('/api/v1/telemetry', json=sample(SESSION)).json()['accepted']


def test_token_sources_and_startup_errors(tmp_path):
    assert load_robot_token(Settings(), {'ROBOT_TOKEN': f' {TOKEN}\n'}) == TOKEN
    secret = tmp_path / 'robot_token'
    secret.write_text(TOKEN + '\n')
    assert load_robot_token(Settings(robot_token_file=str(secret)), {}) == TOKEN
    assert load_robot_token(Settings(robot_token_file=str(secret)), {'ROBOT_TOKEN': 'from-environment-wins-0001'}) == 'from-environment-wins-0001'
    assert load_robot_token(Settings(allow_no_robot_token=True), {}) is None
    with pytest.raises(RuntimeError, match='Set ROBOT_TOKEN'):
        load_robot_token(Settings(), {})
    with pytest.raises(RuntimeError, match='cannot be read'):
        load_robot_token(Settings(robot_token_file=str(tmp_path / 'missing')), {})
    (tmp_path / 'empty').write_text('\n')
    with pytest.raises(RuntimeError, match='empty'):
        load_robot_token(Settings(robot_token_file=str(tmp_path / 'empty')), {})
    with pytest.raises(RuntimeError, match='at least 16'):
        load_robot_token(Settings(), {'ROBOT_TOKEN': 'short'})


def test_config_file_path_enforces_token(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text('{}')
    monkeypatch.setenv('DASHBOARD_CONFIG', str(config))
    monkeypatch.delenv('ROBOT_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='Set ROBOT_TOKEN'):
        create_app()
    monkeypatch.setenv('ROBOT_TOKEN', TOKEN)
    with TestClient(create_app()) as client:
        assert client.post('/api/v1/telemetry', json=sample(SESSION)).status_code == 401
