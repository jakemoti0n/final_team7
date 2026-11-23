"""로봇 하단 디스플레이(/display) 내용: display.json + 팜플렛. 로그인 없이 읽기만, 잘못 고치면 마지막 정상본."""
import json
import logging
import os

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.display import DisplayError, TIMING_DEFAULTS, validate
from server.models import Settings
from server.state import Store
from tests.test_guide import jpeg, png
from tests.test_robots import Clock, write_map

GOOD = {
    "version": 1,
    "message": "쓰레기는 LIMBO에게 주세요.",
    "schedule": [{"date": None, "start": "15:10", "title": "Q&A"},
                 {"date": "2026-11-27", "start": "14:00", "end": "14:30", "title": " 개회 ", "place": "주행사장"}],
}


WRITES = [0]


def write(folder, config, **files):
    folder.mkdir(exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    path = folder / "display.json"
    path.write_text(config if isinstance(config, str) else json.dumps(config, ensure_ascii=False), encoding="utf-8")
    # 아주 짧은 사이에 다시 써도(크기까지 같아도) 바뀐 것으로 보이게 수정시각을 매번 다르게
    WRITES[0] += 1
    os.utime(path, ns=(WRITES[0] * 1_000_000_000, WRITES[0] * 1_000_000_000))


def make(tmp_path, enabled=True, folder="display"):
    settings = Settings(map_yaml=write_map(tmp_path), visitor_enabled=enabled,
                        display_dir=str(tmp_path / folder) if folder else None)
    return TestClient(create_app(settings, Store(settings, Clock(), lambda: "2026-10-13T00:00:00Z")))


def test_validate_fills_defaults_and_sorts():
    view = validate(GOOD)
    assert view["timing"] == TIMING_DEFAULTS and view["slides"] == []
    # 날짜 없는(매일) 일정이 앞, 그다음 날짜·시작 순. 이름 앞뒤 공백은 지운다
    assert [e["title"] for e in view["schedule"]] == ["Q&A", "개회"]
    assert view["schedule"][0] == dict(date=None, start="15:10", end=None, title="Q&A", place=None)
    assert validate({**GOOD, "timing": {"passing_s": 5}})["timing"]["passing_s"] == 5


@pytest.mark.parametrize("change, message", [
    ({"version": 2}, "version"),
    ({"extra": 1}, "needs version"),
    ({"schedule": [{"start": "14:00", "title": "개회", "room": "1"}]}, "Each event"),
    ({"schedule": [{"start": "14:00", "end": "13:00", "title": "개회"}]}, "end must be after start"),
    ({"schedule": [{"start": "24:00", "title": "개회"}]}, "start must look like"),
    ({"schedule": [{"start": "14:00", "date": "11/27", "title": "개회"}]}, "date must look like"),
    ({"schedule": [{"start": "14:00", "title": "줄\n바꿈"}]}, "control characters"),
    ({"message": "가" * 81}, "message must be"),
    ({"slides": ["../users.db"]}, "Slide names"),
    ({"slides": ["a.png", "a.png"]}, "listed twice"),
    ({"timing": {"location_s": 0}}, "location_s"),
    ({"timing": {"location_s": True}}, "location_s"),
    ({"timing": {"fade_s": 1}}, "timing may have"),
])
def test_validate_rejects(change, message):
    with pytest.raises(DisplayError, match=message):
        validate({**GOOD, **change})


def test_content_and_slides(tmp_path):
    write(tmp_path / "display", {**GOOD, "slides": ["b.png", "a.jpg"]}, **{"b.png": png(1920, 1080), "a.jpg": jpeg(1080, 1920),
                                                                       "unlisted.png": png()})
    with make(tmp_path) as client:
        response = client.get("/api/v1/display/content")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-cache"
        body = response.json()
        assert set(body) == {"revision", "message", "schedule", "slides", "timing"}
        assert [(s["file"], s["width"], s["height"], s["type"]) for s in body["slides"]] == [
            ("b.png", 1920, 1080, "image/png"), ("a.jpg", 1080, 1920, "image/jpeg")]
        assert client.get("/api/v1/visitor/state").json()["display"] == body["revision"]
        image = client.get(body["slides"][0]["url"])
        assert image.status_code == 200 and image.content == png(1920, 1080)
        assert image.headers["x-content-type-options"] == "nosniff" and image.headers["content-type"] == "image/png"
        # 폴더에 있어도 목록에 없는 파일, display.json 자체, 경로 장난은 안 된다
        for name in ("unlisted.png", "display.json", "..%2Fdisplay.json", "nope.png"):
            assert client.get(f"/api/v1/display/slides/{name}").status_code == 404, name


def test_bad_edit_keeps_the_last_good_content(tmp_path, caplog):
    folder = tmp_path / "display"
    write(folder, GOOD)
    with make(tmp_path) as client:
        good = client.get("/api/v1/display/content").json()
        with caplog.at_level(logging.ERROR):
            write(folder, '{"version": 1, "schedule": [')        # 저장 중 잘린 파일
            assert client.get("/api/v1/display/content").json() == good
            assert client.get("/api/v1/visitor/state").json()["display"] == good["revision"]
        assert sum("keeping the last good one" in r.getMessage() for r in caplog.records) == 1   # 바뀔 때 한 번만
        # 목록에 적은 그림이 없거나 확장자와 실제 형식이 다르면 역시 잘못된 내용
        write(folder, {**GOOD, "slides": ["missing.png"]})
        assert client.get("/api/v1/display/content").json() == good
        write(folder, {**GOOD, "slides": ["fake.png"]}, **{"fake.png": jpeg()})
        assert client.get("/api/v1/display/content").json() == good
        # 고치면 바로 반영되고 판이 바뀐다
        write(folder, {**GOOD, "message": None})
        fixed = client.get("/api/v1/display/content").json()
        assert fixed["message"] is None and fixed["revision"] != good["revision"]


def test_replacing_only_a_slide_changes_the_revision(tmp_path):
    folder = tmp_path / "display"
    write(folder, {**GOOD, "slides": ["a.png"]}, **{"a.png": png(100, 50)})
    with make(tmp_path) as client:
        first = client.get("/api/v1/display/content").json()
        (folder / "a.png").write_bytes(png(200, 100))
        os.utime(folder / "a.png", ns=(1, 1))                  # 수정시각이 달라지게
        second = client.get("/api/v1/display/content").json()
        assert second["revision"] != first["revision"] and second["slides"][0]["width"] == 200
        assert second["slides"][0]["url"] != first["slides"][0]["url"]   # 주소의 ?v=가 바뀌어 캐시를 피한다


def test_missing_or_invalid_from_the_start(tmp_path):
    with make(tmp_path) as client:                              # 폴더가 없음
        response = client.get("/api/v1/display/content")
        assert response.status_code == 503 and response.json()["error"]["code"] == "display_unavailable"
        assert client.get("/api/v1/visitor/state").json()["display"] is None
    write(tmp_path / "display", {"version": 1})
    with make(tmp_path) as client:
        response = client.get("/api/v1/display/content")
        assert response.status_code == 503 and str(tmp_path) not in response.text   # 서버 경로는 숨긴다


def test_not_configured_or_visitor_disabled(tmp_path):
    write(tmp_path / "display", {**GOOD, "slides": ["a.png"]}, **{"a.png": png()})
    with make(tmp_path, folder=None) as client:
        assert client.get("/api/v1/display/content").json()["error"]["code"] == "display_not_configured"
    with make(tmp_path, enabled=False) as client:
        for path in ("/api/v1/display/content", "/api/v1/display/slides/a.png"):
            response = client.get(path)
            assert response.status_code == 404 and response.json()["error"]["code"] == "visitor_disabled", path


def test_default_content_in_the_repository_is_valid():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[1] / "guides" / "display"
    view = validate(json.loads((folder / "display.json").read_text(encoding="utf-8")))
    assert view["schedule"] and all((folder / name).is_file() for name in view["slides"])
