"""자동 약도: 지도를 읽을 때 만들고, 원본과 영역·크기가 같으며, 잡음은 지우고, 못 만들어도 지도는 쓴다"""
import re

from fastapi.testclient import TestClient
import numpy as np

from server import sketch
from server.app import create_app
from server.models import Settings
from server.state import Store

FREE, UNKNOWN, WALL = 254, 205, 0


def room_map(tmp_path, *, rays=True, speck=True, blob=True):
    """40×30 px (0.05 m → 2 m × 1.5 m): 벽으로 둘린 방, 밖으로 뻗은 1 px 레이저 줄무늬, 방 안 작은 점, 떨어진 작은 빈 칸"""
    image = np.full((30, 40), UNKNOWN, np.uint8)
    image[4:26, 4:36] = WALL
    image[5:25, 5:35] = FREE
    if rays:
        image[14, 35:40] = FREE          # 벽 밖으로 뻗은 줄무늬
        image[0:5, 20] = FREE
    if speck:
        image[12:14, 12:14] = WALL       # 방 안의 의자 같은 점
    if blob:
        image[27:30, 0:3] = FREE         # 구석의 작은 빈 칸 (waypoint 없음)
    (tmp_path / 'm.pgm').write_bytes(b'P5\n40 30\n255\n' + image.tobytes())
    (tmp_path / 'm.yaml').write_text('image: m.pgm\nresolution: 0.05\norigin: [-1.0, -0.5, 0.0]\n')
    return image


def test_cells_drop_rays_specks_and_far_blobs(tmp_path):
    image = room_map(tmp_path)
    cells, size = sketch.floor_cells(40, 30, image.tobytes(), 0.05)
    assert size == 5 and cells.shape == (6, 8)     # 0.25 m 칸, 남는 픽셀은 칸 하나로 올림
    expected = np.zeros((6, 8), bool)
    expected[1:5, 1:7] = True                      # 방(5..25 행, 5..35 열)만 남는다
    assert (cells == expected).all()


def test_speck_in_a_narrow_corridor_does_not_cut_it():
    """0.8 m 폭 복도 한가운데의 10 cm 점: 메운 뒤에 줄무늬를 지우므로 복도가 이어진 채 남는다"""
    image = np.full((30, 60), UNKNOWN, np.uint8)
    image[5:21, 0:60] = FREE
    image[12:14, 30:32] = WALL
    cells, _ = sketch.floor_cells(60, 30, image.tobytes(), 0.05)
    assert cells[1:4, :].all()


def test_waypoint_keeps_a_small_area(tmp_path):
    image = np.full((30, 40), UNKNOWN, np.uint8)
    image[1:17, 1:17] = FREE        # 0.8 m 칸 (작은 쪽)
    image[1:29, 20:39] = FREE       # 큰 방
    pgm = image.tobytes()
    big_only, _ = sketch.floor_cells(40, 30, pgm, 0.05)
    assert not big_only[:, :3].any() and big_only[:, 4:].any()
    kept, _ = sketch.floor_cells(40, 30, pgm, 0.05, keep_px=[(8, 8)])
    assert kept[:, :3].any() and kept[:, 4:].any()


def test_svg_has_the_original_size_and_no_script(tmp_path):
    image = room_map(tmp_path)
    body = sketch.svg(40, 30, image.tobytes(), 0.05, [-1.0, -0.5, 0.0]).decode()
    assert body.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30" viewBox="0 0 40 30">')
    assert '<script' not in body and 'href' not in body
    # 바닥은 방 하나(직사각형), 경계는 가로 2줄·세로 2줄
    floor = re.search(r'<path d="([^"]*)" fill="#FFFFFF"', body).group(1)
    assert floor == 'M5 5h30v20h-30z'
    walls = re.search(r'<path d="([^"]*)" stroke="#2E3A33"', body).group(1)
    assert sorted(re.findall(r'M[^M]+', walls)) == sorted(['M5 5H35', 'M5 25H35', 'M5 5V25', 'M35 5V25'])


def test_map_api_serves_the_sketch(tmp_path):
    room_map(tmp_path)
    store = Store(Settings(map_yaml=str(tmp_path / 'm.yaml')))
    with TestClient(create_app(store.settings, store)) as client:
        meta = client.get('/api/v1/map').json()
        assert meta['sketch'] == '/api/v1/map_sketch.svg?robot_id=LIMBO-01'
        response = client.get(meta['sketch'])
        assert response.status_code == 200 and response.headers['content-type'] == 'image/svg+xml'
        assert "default-src 'none'" in response.headers['content-security-policy']
        assert response.content.startswith(b'<svg') and b'viewBox="0 0 40 30"' in response.content
        assert client.get('/api/v1/map_sketch.svg', params={'robot_id': 'NOPE'}).status_code == 404


def test_map_still_loads_when_sketch_fails(tmp_path, monkeypatch):
    room_map(tmp_path)
    def broken(*args, **kwargs):
        raise ValueError('boom')
    monkeypatch.setattr(sketch, 'svg', broken)
    store = Store(Settings(map_yaml=str(tmp_path / 'm.yaml')))
    with TestClient(create_app(store.settings, store)) as client:
        meta = client.get('/api/v1/map').json()
        assert meta['sketch'] is None and meta['width'] == 40
        assert client.get('/api/v1/map.png').status_code == 200
        assert client.get('/api/v1/map_sketch.svg').json()['error']['code'] == 'map_sketch_unavailable'


def test_project_maps_make_sketches():
    """저장소의 실제 지도도 약도가 나오고 바닥이 남는다 (잡음 제거가 지도를 다 지우지 않는다)"""
    from server import mapdata
    for name in ('human_test_map', 'real_open_space_20261111', 'aischool_2f_map'):
        meta, _, body = mapdata.load(f'limbo/src/limbo_navigation/maps/{name}.yaml', base='..')
        assert body is not None and f'viewBox="0 0 {meta["width"]} {meta["height"]}"' in body.decode()
        assert re.search(r'<path d="M[^"]+" fill="#FFFFFF"', body.decode())
