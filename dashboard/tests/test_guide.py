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
    marked = {**guide, 'markers': [{'name': 'x', 'category': 'other', 'x': '__INF__', 'y': 0}]}
    guide_text = json.dumps(marked).replace('"__INF__"', 'Infinity')
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


# ---- 약도 그림 (메인 약도를 그림 파일로) ----

import os
import struct as _struct
import time

from server import mapdata


def png(width=40, height=30):
    return mapdata.png_gray(width, height, bytes(width * height))


def jpeg(width=64, height=48):
    app0 = b'\xff\xe0' + _struct.pack('>H', 16) + b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    sof = b'\xff\xc0' + _struct.pack('>HBHHB', 11, 8, height, width, 1) + b'\x01\x11\x00'
    return b'\xff\xd8' + app0 + sof + b'\xff\xd9'


def webp_vp8x(width=300, height=200):
    body = b'VP8X' + _struct.pack('<I', 10) + b'\x00\x00\x00\x00' + (width - 1).to_bytes(3, 'little') + (height - 1).to_bytes(3, 'little')
    return b'RIFF' + _struct.pack('<I', 4 + len(body)) + b'WEBP' + body


def webp_lossless(width=17, height=9):
    bits = (width - 1) | ((height - 1) << 14)
    body = b'VP8L' + _struct.pack('<I', 5) + b'\x2f' + bits.to_bytes(4, 'little')
    return b'RIFF' + _struct.pack('<I', 4 + len(body)) + b'WEBP' + body


def upload(client, data, kind='image/png'):
    return client.put('/api/v1/guide/image', content=data, headers={'content-type': kind})


def placed(info, transform=None):
    """그리기 영역(-10..20) 안에 0.1 m/px로 놓은 그림"""
    return {'file': info['file'], 'width': info['width'], 'height': info['height'],
            'transform': transform or [0.1, 0, -5, 0, -0.1, 15], 'points': [], 'show_areas': False}


@pytest.mark.parametrize('maker,kind,ext,size', [
    (png, 'image/png', 'png', (40, 30)), (jpeg, 'image/jpeg', 'jpg', (64, 48)),
    (webp_vp8x, 'image/webp', 'webp', (300, 200)), (webp_lossless, 'image/webp', 'webp', (17, 9))])
def test_upload_reads_type_and_size(rig, maker, kind, ext, size):
    client, path = rig
    data = maker()
    response = upload(client, data, kind)
    assert response.status_code == 201, response.json()
    info = response.json()
    assert info['file'] == f"image-{hashlib.sha256(data).hexdigest()[:16]}.{ext}" and (info['width'], info['height']) == size
    assert (path.parent / 'map_guide_files' / info['file']).read_bytes() == data
    served = client.get(f"/api/v1/guide/image/{info['file']}")
    assert served.content == data and served.headers['content-type'] == kind
    assert served.headers['x-content-type-options'] == 'nosniff' and "default-src 'none'" in served.headers['content-security-policy']


def test_upload_rejects_other_files(rig):
    client, _ = rig
    assert upload(client, b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml').status_code == 415
    bad = upload(client, b'GIF89a' + bytes(20), 'image/png')
    assert bad.status_code == 422 and bad.json()['error']['code'] == 'invalid_image'
    assert upload(client, png()[:20], 'image/png').status_code == 422                       # 잘린 PNG
    huge = upload(client, png() + bytes(guide_module.MAX_IMAGE_BYTES), 'image/png')
    assert huge.status_code == 413
    assert client.get('/api/v1/guide/image/image-0000000000000000.png').status_code == 404
    assert client.get('/api/v1/guide/image/..%2Fmap.yaml').status_code == 404


def test_guide_with_image_saves_and_checks_it(rig):
    client, path = rig
    info = upload(client, png()).json()
    guide = client.get('/api/v1/guide').json()['guide']
    assert guide['image'] is None
    guide['image'] = placed(info)
    guide['image']['points'] = [{'image': [0, 0], 'map': [-5, 15]}]
    saved = client.put('/api/v1/guide', json={'revision': '', 'guide': guide})
    assert saved.status_code == 200, saved.json()
    image = saved.json()['guide']['image']
    assert image['transform'] == [0.1, 0, -5, 0, -0.1, 15] and image['points'][0]['map'] == [-5, 15]
    assert yaml.safe_load(path.read_text(encoding='utf-8'))['image']['file'] == info['file']
    revision = saved.json()['revision']
    for change, reason in [
        (dict(transform=[0.1, 0, -5, 0, -0.1, 50]), 'inside bounds'),        # 영역 밖
        (dict(transform=[0.1, 0.1, 0, 0.1, 0.1, 0]), 'flatten'),            # 납작한 변환
        (dict(transform=[0.1, 0, 0, 0, -0.1]), '6 numbers'),
        (dict(file='../map.yaml'), 'upload'),
        (dict(file='image-ffffffffffffffff.png'), 'missing'),                # 올리지 않은 그림
        (dict(width=0), 'width'),
        (dict(show_areas='yes'), 'show_areas'),
    ]:
        broken = {**guide, 'image': {**guide['image'], **change}}
        response = client.put('/api/v1/guide', json={'revision': revision, 'guide': broken})
        assert response.status_code == 422 and reason in response.json()['error']['message'], (change, response.json())


def test_old_guide_files_without_image_still_load(rig):
    client, path = rig
    path.parent.mkdir()
    path.write_text('version: 1\nmap: map.yaml\nbounds: {x_min: 0, y_min: 0, x_max: 10, y_max: 10}\n'
                    'categories: [{key: other, label: 기타, color: "#FFFFFF", icon: none}]\nareas: []\nmarkers: []\n')
    assert client.get('/api/v1/guide').json()['guide']['image'] is None


def test_unused_images_are_pruned_after_an_hour(rig):
    client, path = rig
    old = upload(client, png(10, 10)).json()['file']
    fresh = upload(client, png(11, 11)).json()['file']
    used = upload(client, png(12, 12)).json()
    files = path.parent / 'map_guide_files'
    hour_ago = time.time() - 7200
    for name in (old, used['file']):
        os.utime(files / name, (hour_ago, hour_ago))
    guide = client.get('/api/v1/guide').json()['guide']
    guide['image'] = placed(used)
    assert client.put('/api/v1/guide', json={'revision': '', 'guide': guide}).status_code == 200
    assert sorted(p.name for p in files.iterdir()) == sorted([fresh, used['file']])   # 쓰는 것·막 올린 것은 남음
