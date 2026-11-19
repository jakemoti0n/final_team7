"""방문자 안내 약도 파일(guide_yaml): 없으면 빈 약도, 저장은 revision 검사·원자적 교체, 지도보다 넓게 그릴 수 있음"""
import copy
import hashlib

from fastapi.testclient import TestClient
import pytest
import yaml

from server import guide as guide_module
from server.app import create_app
from server.models import Settings
from server.state import Store


def write_map(tmp_path):
    (tmp_path / 'map.pgm').write_bytes(b'P5\n10 10\n255\n' + bytes([254]) * 100)
    (tmp_path / 'map.yaml').write_text('image: map.pgm\nresolution: 1\norigin: [0, 0, 0]\n')
    return str(tmp_path / 'map.yaml')


@pytest.fixture
def rig(tmp_path):
    path = tmp_path / 'guides' / 'map_guide.yaml'      # 폴더가 없어도 처음 저장할 때 만든다
    store = Store(Settings(map_yaml=write_map(tmp_path), guide_yaml=str(path)))
    with TestClient(create_app(store.settings, store)) as client:
        yield client, path


def room(name='201 강의실', category='classroom', polygon=None):
    return {'name': name, 'category': category, 'polygon': polygon or [[1, 1], [4, 1], [4, 3], [1, 3]]}


def test_missing_file_is_an_empty_guide_with_wider_bounds(rig):
    client, path = rig
    doc = client.get('/api/v1/guide').json()
    assert doc['exists'] is False and doc['revision'] == '' and doc['file'] == 'map_guide.yaml'
    assert doc['map'] == 'map.yaml' and doc['map_matches'] is True
    assert doc['map_bounds'] == {'x_min': 0, 'y_min': 0, 'x_max': 10, 'y_max': 10}
    guide = doc['guide']
    assert guide['bounds'] == {'x_min': -10, 'y_min': -10, 'x_max': 20, 'y_max': 20}   # 지도보다 사방 10 m
    assert guide['map'] == 'map.yaml' and guide['areas'] == [] and guide['markers'] == []
    assert [c['label'] for c in guide['categories']][:4] == ['강의실', '행사장', '화장실', '입구']
    assert not path.exists()
    assert client.get('/api/v1/guide/file').json()['error']['code'] == 'guide_not_saved'


def test_save_creates_the_file_and_checks_revision(rig):
    client, path = rig
    guide = client.get('/api/v1/guide').json()['guide']
    guide['areas'] = [room(' 201 강의실 '), room('바깥 창고', 'other', [[-8, -8], [-2, -8], [-5, -3]])]  # 지도 밖도 그릴 수 있음
    guide['markers'] = [{'name': '정문', 'category': 'entrance', 'x': 0.12345, 'y': 15}]
    guide['categories'].append({'key': 'lounge-2', 'label': '휴게실', 'color': '#abcdef', 'icon': 'food'})
    saved = client.put('/api/v1/guide', json={'revision': '', 'guide': guide})
    assert saved.status_code == 200, saved.json()
    doc = saved.json()
    assert doc['exists'] is True and doc['revision'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert doc['guide']['areas'][0]['name'] == '201 강의실'                    # 앞뒤 공백 제거
    assert doc['guide']['markers'][0]['x'] == 0.123                            # mm 단위
    assert doc['guide']['categories'][-1]['color'] == '#ABCDEF'
    on_disk = yaml.safe_load(path.read_text(encoding='utf-8'))
    assert on_disk == doc['guide'] and '201 강의실' in path.read_text(encoding='utf-8')   # 한글 그대로
    assert client.get('/api/v1/guide').json() == doc
    # 다른 화면이 먼저 저장했으면 거절
    stale = client.put('/api/v1/guide', json={'revision': '', 'guide': guide})
    assert stale.status_code == 409 and stale.json()['error']['code'] == 'revision_conflict'
    guide['areas'] = []
    assert client.put('/api/v1/guide', json={'revision': doc['revision'], 'guide': guide}).json()['guide']['areas'] == []
    download = client.get('/api/v1/guide/file')
    assert download.content == path.read_bytes() and download.headers['content-type'].startswith('application/yaml')
    assert download.headers['content-disposition'] == 'attachment; filename="map_guide.yaml"'


def bad(change):
    def apply(guide):
        change(guide)
        return guide
    return apply


BAD_GUIDES = {
    'unknown category': bad(lambda g: g['areas'].append(room(category='nope'))),
    'crossing edges': bad(lambda g: g['areas'].append(room(polygon=[[0, 0], [4, 4], [4, 0], [0, 4]]))),
    'flat shape': bad(lambda g: g['areas'].append(room(polygon=[[0, 0], [2, 0], [4, 0]]))),
    'repeated point': bad(lambda g: g['areas'].append(room(polygon=[[0, 0], [2, 0], [2, 2], [2, 0]]))),
    'two points': bad(lambda g: g['areas'].append(room(polygon=[[0, 0], [2, 0]]))),
    'outside bounds': bad(lambda g: g['areas'].append(room(polygon=[[0, 0], [30, 0], [30, 3]]))),
    'marker outside': bad(lambda g: g['markers'].append({'name': 'x', 'category': 'other', 'x': 50, 'y': 0})),
    'too many points': bad(lambda g: g['areas'].append(room(polygon=[[i * .1, (i % 2) * .1 + i * .01] for i in range(65)]))),
    'control character': bad(lambda g: g['areas'].append(room(name='a\nb'))),
    'empty name': bad(lambda g: g['areas'].append(room(name='   '))),
    'long name': bad(lambda g: g['areas'].append(room(name='가' * 33))),
    'extra field': bad(lambda g: g['areas'].append({**room(), 'color': 'red'})),
    'not a number': bad(lambda g: g['markers'].append({'name': 'x', 'category': 'other', 'x': True, 'y': 0})),
    'bad color': bad(lambda g: g['categories'].append({'key': 'k', 'label': 'K', 'color': 'red', 'icon': 'none'})),
    'script color': bad(lambda g: g['categories'].append({'key': 'k', 'label': 'K', 'color': '#fff"/><script>', 'icon': 'none'})),
    'bad icon': bad(lambda g: g['categories'].append({'key': 'k', 'label': 'K', 'color': '#FFFFFF', 'icon': 'rocket'})),
    'duplicate key': bad(lambda g: g['categories'].append({**g['categories'][0], 'label': '또'})),
    'bad key': bad(lambda g: g['categories'].append({'key': 'Big Key', 'label': 'K', 'color': '#FFFFFF', 'icon': 'none'})),
    'no categories': bad(lambda g: g.update(categories=[])),
    'empty bounds': bad(lambda g: g['bounds'].update(x_max=g['bounds']['x_min'])),
    'huge bounds': bad(lambda g: g['bounds'].update(x_max=5000)),
    'wrong version': bad(lambda g: g.update(version=2)),
    'missing markers': bad(lambda g: g.pop('markers')),
}


@pytest.mark.parametrize('name', BAD_GUIDES)
def test_invalid_guides_are_rejected_and_file_untouched(rig, name):
    client, path = rig
    guide = BAD_GUIDES[name](copy.deepcopy(client.get('/api/v1/guide').json()['guide']))
    response = client.put('/api/v1/guide', json={'revision': '', 'guide': guide})
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_guide', response.json()
    assert not path.exists()


def test_bad_payloads(rig):
    client, _ = rig
    guide = client.get('/api/v1/guide').json()['guide']
    # 서버의 JSON 해석은 Infinity·NaN 글자를 받아들이므로 좌표 검사에서 걸러야 한다
    import json
    guide_text = json.dumps(guide)[:-len(']}')] + ', {"name": "x", "category": "other", "x": Infinity, "y": 0}]}'
    assert guide_text.count('"markers": [, ') == 1
    guide_text = guide_text.replace('"markers": [, ', '"markers": [')
    body = '{"revision": "", "guide": ' + guide_text + '}'
    response = client.put('/api/v1/guide', content=body.encode(), headers={'content-type': 'application/json'})
    assert response.status_code == 422 and response.json()['error']['code'] == 'invalid_guide'
    assert client.put('/api/v1/guide', json={'guide': guide}).json()['error']['code'] == 'invalid_payload'
    assert client.put('/api/v1/guide', json={'revision': '', 'guide': guide, 'x': 1}).status_code == 422
    assert client.put('/api/v1/guide', content=b'{}', headers={'content-type': 'text/plain'}).status_code == 415


def test_large_guides_fit_but_size_is_capped(rig):
    """waypoint보다 큰 본문(8 KiB 넘음)도 받되 256 KiB에서 자른다"""
    client, _ = rig
    guide = client.get('/api/v1/guide').json()['guide']
    guide['areas'] = [room(f'방 {i}', polygon=[[1 + i * .01, 1], [4, 1], [4, 3], [1, 3]]) for i in range(300)]
    response = client.put('/api/v1/guide', json={'revision': '', 'guide': guide})
    assert response.status_code == 200 and len(response.json()['guide']['areas']) == 300
    big = {'revision': response.json()['revision'], 'guide': guide, 'pad': 'x' * guide_module.MAX_BYTES}
    assert client.put('/api/v1/guide', json=big).status_code == 413


def test_broken_file_is_reported_and_can_be_overwritten(rig):
    client, path = rig
    path.parent.mkdir()
    path.write_text('version: 1\nareas: [oops\n')
    broken = client.get('/api/v1/guide')
    assert broken.status_code == 503 and broken.json()['error']['code'] == 'guide_unavailable'
    guide = guide_module.empty_guide({'origin': [0, 0], 'width': 10, 'height': 10, 'resolution': 1}, 'map.yaml')
    revision = hashlib.sha256(path.read_bytes()).hexdigest()
    assert client.put('/api/v1/guide', json={'revision': revision, 'guide': guide}).status_code == 200
    assert client.get('/api/v1/guide').status_code == 200


def test_guide_drawn_for_another_map_is_flagged(rig):
    client, _ = rig
    guide = client.get('/api/v1/guide').json()['guide']
    guide['map'] = 'other_map.yaml'
    assert client.put('/api/v1/guide', json={'revision': '', 'guide': guide}).json()['map_matches'] is False


def test_not_configured(tmp_path):
    for settings in (Settings(map_yaml=write_map(tmp_path)),                          # guide_yaml 없음
                     Settings(guide_yaml=str(tmp_path / 'g.yaml'))):                  # 지도 없음 (그릴 기준이 없다)
        store = Store(settings)
        with TestClient(create_app(store.settings, store)) as client:
            for method, path in (('get', '/api/v1/guide'), ('put', '/api/v1/guide'), ('get', '/api/v1/guide/file')):
                response = getattr(client, method)(path, **({'json': {}} if method == 'put' else {}))
                assert response.json()['error']['code'] == 'guide_not_configured'


def test_project_config_points_to_a_writable_guide_folder():
    """로컬 설정은 dashboard/guides/, 컨테이너 설정은 볼륨 /data/guide.yaml"""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / 'config.json').read_text())['guide_yaml'].startswith('dashboard/guides/')
    assert json.loads((root / 'deploy' / 'config.json').read_text())['guide_yaml'] == '/data/guide.yaml'
