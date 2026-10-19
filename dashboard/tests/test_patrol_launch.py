"""Patrol start is tested with a fake process, never a live ROS node."""
import signal
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from server.app import create_app
from server.models import Settings
from server.patrol_launch import PatrolLauncher, LaunchError
from server.state import Store
from server.waypoints import WaypointFile


class Process:
    pid = 1234
    def poll(self):
        return None


def files(tmp_path):
    map_meta = {'origin': [0, 0, 0], 'width': 10, 'height': 10, 'resolution': 1}
    route = tmp_path / 'route.yaml'
    route.write_text(yaml.safe_dump({'waypoints': [{'name': 'A', 'type': 'stop', 'x': 1, 'y': 1, 'yaw': 0, 'wait_sec': 0}]}))
    workspace = tmp_path / 'workspace'
    (workspace / 'install').mkdir(parents=True)
    (workspace / 'install/setup.bash').write_text('')
    executable = workspace / 'install/limbo_patrol/lib/limbo_patrol/patrol_node'
    executable.parent.mkdir(parents=True)
    executable.write_text('')
    ros = tmp_path / 'ros_setup.bash'
    ros.write_text('')
    return WaypointFile(route, map_meta), workspace, ros


def test_launcher_passes_edited_file_and_domain_to_ros(tmp_path):
    route, workspace, ros = files(tmp_path)
    calls = []
    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return Process()
    launcher = PatrolLauncher(route, 97, workspace, ros, fake_popen)
    launcher._other_patrol_running = lambda: False
    result = launcher.start()
    args, options = calls[0]
    assert str(route.path) in args
    assert str(workspace / 'install/limbo_patrol/lib/limbo_patrol/patrol_node') in args
    assert 'exec "$3"' in args[2]
    assert args[-1] == 'true'
    assert options['env']['ROS_DOMAIN_ID'] == '97'
    assert result['waypoints_file'] == str(route.path)
    assert launcher.status()['status'] == 'running'
    try:
        launcher.start()
        assert False, 'duplicate patrol must be rejected'
    except LaunchError as exc:
        assert exc.code == 'patrol_already_running'


def test_start_api_gates_on_bridge_and_patrol_state(tmp_path):
    route, workspace, ros = files(tmp_path)
    settings = Settings(map_yaml=str(tmp_path / 'map.yaml'), waypoints_yaml=str(route.path), patrol_ros_domain_id=97)
    (tmp_path / 'map.pgm').write_bytes(b'P5\n10 10\n255\n' + bytes([205]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    store = Store(settings)
    app = create_app(settings, store)
    launched = []
    app.state.patrol_launcher.start = lambda sim: launched.append(sim) or {'status': 'starting'}
    with TestClient(app) as client:
        assert client.post('/api/v1/patrol/start').json()['error']['code'] == 'bridge_not_connected'
        store.connection = lambda now=None: ('connected', 0)
        assert client.post('/api/v1/patrol/start').json()['error']['code'] == 'patrol_state_unavailable'
        store.payload = {'patrol': {'state': 'patrolling'}}
        assert client.post('/api/v1/patrol/start').json()['error']['code'] == 'patrol_already_running'
        store.payload = {'patrol': {'state': None}}
        response = client.post('/api/v1/patrol/start')
        assert response.status_code == 202
        assert launched == [True]
        store.payload = {'patrol': {'state': 'patrolling'}}
        app.state.patrol_launcher.status = lambda: {'status': 'exited'}
        assert client.post('/api/v1/patrol/start').status_code == 202
        assert launched == [True, True]


def test_stop_only_signals_dashboard_child_process(tmp_path):
    route, workspace, ros = files(tmp_path)
    launcher = PatrolLauncher(route, 97, workspace, ros, lambda *args, **kwargs: Process())
    try:
        launcher.stop()
        assert False, 'idle patrol must not be stopped'
    except LaunchError as exc:
        assert exc.code == 'patrol_not_running'
    launcher._other_patrol_running = lambda: False
    launcher.start()
    with patch('server.patrol_launch.os.killpg') as killpg:
        assert launcher.stop()['status'] == 'stopping'
    killpg.assert_called_once_with(1234, signal.SIGTERM)


def test_stop_api_only_controls_dashboard_started_patrol(tmp_path):
    route, workspace, ros = files(tmp_path)
    settings = Settings(map_yaml=str(tmp_path / 'map.yaml'), waypoints_yaml=str(route.path), patrol_ros_domain_id=97)
    (tmp_path / 'map.pgm').write_bytes(b'P5\n10 10\n255\n' + bytes([205]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    app = create_app(settings, Store(settings))
    with TestClient(app) as client:
        assert client.post('/api/v1/patrol/stop').json()['error']['code'] == 'patrol_not_running'
        app.state.patrol_launcher.stop = lambda: {'status': 'stopping', 'pid': 1234}
        response = client.post('/api/v1/patrol/stop')
        assert response.status_code == 202
        assert response.json()['status'] == 'stopping'
