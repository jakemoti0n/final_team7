"""Live route updates use a temporary file, never the tracked patrol route."""
import yaml
from fastapi.testclient import TestClient

from server.app import create_app
from server.models import Settings


def route_client(tmp_path):
    pgm = tmp_path / 'map.pgm'
    pgm.write_bytes(b'P5\n10 10\n255\n' + bytes([205]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    path = tmp_path / 'route.yaml'
    path.write_text(yaml.safe_dump({'waypoints': [
        {'name': 'A', 'type': 'pass', 'x': 2, 'y': 2, 'yaw': 90, 'wait_sec': 3},
        {'name': 'B', 'type': 'stop', 'x': 4, 'y': 4, 'yaw': -30, 'wait_sec': 5},
    ]}))
    return TestClient(create_app(Settings(map_yaml=str(tmp_path / 'map.yaml'), waypoints_yaml=str(path)))), path


def test_add_move_delete_persist_and_keep_patrol_fields(tmp_path):
    client, path = route_client(tmp_path)
    with client:
        before = client.get('/api/v1/waypoints').json()
        added = client.put('/api/v1/waypoints', json={'revision': before['revision'], 'action': 'add',
                       'waypoint': {'name': 'C', 'type': 'pass', 'x': 3, 'y': 3}})
        assert added.status_code == 200, added.text
        doc = added.json()
        assert [p['name'] for p in doc['waypoints']] == ['A', 'C', 'B']
        assert doc['waypoints'][1]['yaw'] == 0
        moved = client.put('/api/v1/waypoints', json={'revision': doc['revision'], 'action': 'move',
                            'name': 'B', 'x': 5, 'y': 6})
        assert moved.status_code == 200
        assert moved.json()['waypoints'][-1]['yaw'] == -30
        assert moved.json()['waypoints'][-1]['wait_sec'] == 5
        assert client.get('/api/v1/map').json()['waypoints'][-1]['x'] == 5
        deleted = client.put('/api/v1/waypoints', json={'revision': moved.json()['revision'],
                             'action': 'delete', 'name': 'C'})
        assert deleted.status_code == 200
        assert [p['name'] for p in yaml.safe_load(path.read_text())['waypoints']] == ['A', 'B']


def test_invalid_changes_and_revision_do_not_touch_file(tmp_path):
    client, path = route_client(tmp_path)
    with client:
        revision = client.get('/api/v1/waypoints').json()['revision']
        original = path.read_bytes()
        requests = [
            {'action': 'delete', 'name': 'B'},
            {'action': 'add', 'waypoint': {'name': 'A', 'type': 'stop', 'x': 2, 'y': 2}},
            {'action': 'move', 'name': 'A', 'x': 99, 'y': 2},
            {'action': 'move', 'name': 'A', 'x': True, 'y': 2},
        ]
        for change in requests:
            response = client.put('/api/v1/waypoints', json={'revision': revision, **change})
            assert response.status_code in (409, 422), response.text
            assert path.read_bytes() == original
        path.write_text(path.read_text() + '\n# external edit\n')
        response = client.put('/api/v1/waypoints', json={'revision': revision, 'action': 'delete', 'name': 'A'})
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'revision_conflict'


def test_symlink_target_remains_linked(tmp_path):
    client, path = route_client(tmp_path)
    link = tmp_path / 'installed.yaml'
    link.symlink_to(path)
    with TestClient(create_app(Settings(map_yaml=str(tmp_path / 'map.yaml'), waypoints_yaml=str(link)))) as linked:
        revision = linked.get('/api/v1/waypoints').json()['revision']
        response = linked.put('/api/v1/waypoints', json={'revision': revision, 'action': 'move', 'name': 'A', 'x': 7, 'y': 2})
        assert response.status_code == 200
        assert link.is_symlink()
        assert yaml.safe_load(path.read_text())['waypoints'][0]['x'] == 7


def test_rename_and_reorder_persist_without_changing_other_fields(tmp_path):
    client, path = route_client(tmp_path)
    with client:
        revision = client.get('/api/v1/waypoints').json()['revision']
        renamed = client.put('/api/v1/waypoints', json={'revision': revision, 'action': 'rename',
                             'name': 'A', 'new_name': '첫 지점'})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()['waypoints'][0]['yaw'] == 90
        # Add another stop so moving the former final stop is allowed.
        added = client.put('/api/v1/waypoints', json={'revision': renamed.json()['revision'],
                           'action': 'add', 'waypoint': {'name': 'C', 'type': 'stop', 'x': 7, 'y': 7}})
        reordered = client.put('/api/v1/waypoints', json={'revision': added.json()['revision'],
                               'action': 'reorder', 'order': ['B', '첫 지점', 'C']})
        assert reordered.status_code == 200, reordered.text
        assert [p['name'] for p in yaml.safe_load(path.read_text())['waypoints']] == ['B', '첫 지점', 'C']
        assert reordered.json()['waypoints'][0]['wait_sec'] == 5
        assert [p['name'] for p in client.get('/api/v1/map').json()['waypoints']] == ['B', '첫 지점', 'C']


def test_invalid_rename_or_order_does_not_change_file(tmp_path):
    client, path = route_client(tmp_path)
    with client:
        revision = client.get('/api/v1/waypoints').json()['revision']
        original = path.read_bytes()
        changes = [
            {'action': 'rename', 'name': 'A', 'new_name': 'B'},
            {'action': 'rename', 'name': 'A', 'new_name': '  '},
            {'action': 'rename', 'name': 'A', 'new_name': 'x' * 33},
            {'action': 'reorder', 'order': ['B', 'A']},
            {'action': 'reorder', 'order': ['A', 'A']},
            {'action': 'reorder', 'order': ['A']},
            {'action': 'reorder', 'order': ['A', 'B', 'C']},
        ]
        for change in changes:
            response = client.put('/api/v1/waypoints', json={'revision': revision, **change})
            assert response.status_code in (409, 422), response.text
            assert path.read_bytes() == original


def test_active_patrol_rejects_every_waypoint_change(tmp_path):
    client, path = route_client(tmp_path)
    with client:
        revision = client.get('/api/v1/waypoints').json()['revision']
        original = path.read_bytes()
        for state in ('waiting_localization', 'patrolling', 'pausing', 'paused'):
            client.app.state.store.payload = {'patrol': {'state': state}}
            response = client.put('/api/v1/waypoints', json={'revision': revision, 'action': 'rename', 'name': 'A', 'new_name': 'Changed'})
            assert response.status_code == 409
            assert response.json()['error']['code'] == 'patrol_active'
            assert path.read_bytes() == original
        client.app.state.store.payload = {'patrol': {'state': 'completed'}}
        response = client.put('/api/v1/waypoints', json={'revision': revision, 'action': 'rename', 'name': 'A', 'new_name': 'Changed'})
        assert response.status_code == 200
