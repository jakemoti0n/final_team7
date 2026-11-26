"""분리수거 성공률 (POST /api/v1/eco → visitor/state의 eco, 하단 디스플레이 장면 ⑤ 나무 3상태).
근거: signage/docs/PRD_로봇_하단_디스플레이_v0.3.md 「분리수거 성공률 계약」"""
import logging

import pytest
from fastapi.testclient import TestClient

from server.app import create_app, load_eco_token
from server.display import DisplayError, validate as validate_display
from server.eco import EcoError, judge, validate
from server.models import Settings
from server.state import Store
from tests.test_robots import Clock, write_map

TOKEN = "eco-token-0123456789"
GOOD = {
    "schema_version": 1,
    "observed_at": "2026-10-13T09:00:00+09:00",   # = 서버 시각 2026-10-13T00:00:00Z
    "window_start": "2026-10-13T06:00:00+09:00",
    "window_end": "2026-10-13T09:00:00+09:00",
    "source": "rpi-sorter",
    "evaluation_method": "ai_bin_inspection",
    "verified_correct_count": 18,
    "verified_total_count": 20,
    "quality": "ok",
}


def make(tmp_path, eco_token=TOKEN, **settings):
    clock = Clock()
    s = Settings(map_yaml=write_map(tmp_path), visitor_enabled=True, **settings)
    client = TestClient(create_app(s, Store(s, clock, lambda: "2026-10-13T00:00:00Z"), eco_token=eco_token))
    return client, clock


def send(client, body, token=TOKEN):
    return client.post("/api/v1/eco", json=body, headers={"Authorization": f"Bearer {token}"} if token else {})


def eco(client):
    return client.get("/api/v1/visitor/state").json()["eco"]


def test_positive_negative_and_numbers(tmp_path):
    client, _ = make(tmp_path)
    with client:
        response = send(client, GOOD)
        assert response.status_code == 200
        shown = dict(state="positive", rate_percent=90, correct=18, total=20, method="ai_bin_inspection")
        assert response.json() == {"accepted": True, "eco": shown}
        assert eco(client) == shown
        # 80 % 바로 아래는 부정. 보이는 숫자는 내림이라 기준 아래로 보인다 (79.9 → 79)
        send(client, {**GOOD, "verified_correct_count": 799, "verified_total_count": 1000})
        assert eco(client)["state"] == "negative" and eco(client)["rate_percent"] == 79
        send(client, {**GOOD, "verified_correct_count": 16})
        assert eco(client)["state"] == "positive" and eco(client)["rate_percent"] == 80


@pytest.mark.parametrize("change", [
    {"quality": "degraded"},                                         # Pi가 스스로 믿을 수 없다고 함
    {"evaluation_method": "model_prediction"},                       # 넣기 전 예측만으로 센 건수
    {"verified_correct_count": 19, "verified_total_count": 19},     # 표본 부족 (20건 미만)
    {"verified_correct_count": None, "verified_total_count": None},  # 셀 수 없음
])
def test_initial_without_numbers(tmp_path, change):
    client, _ = make(tmp_path)
    with client:
        assert send(client, {**GOOD, **change}).status_code == 200
        assert eco(client) == {"state": "initial"}


def test_stale_by_server_receive_time_not_sender_clock(tmp_path):
    client, clock = make(tmp_path)
    with client:
        # Pi 시계가 하루 늦어도 서버가 방금 받았으면 판정한다
        send(client, {**GOOD, "observed_at": "2026-10-12T09:00:00+09:00",
                      "window_start": "2026-10-12T06:00:00+09:00", "window_end": "2026-10-12T09:00:00+09:00"})
        assert eco(client)["state"] == "positive"
        clock.now = 600
        assert eco(client)["state"] == "positive"
        clock.now = 600.5   # 마지막으로 받은 뒤 600 s가 지나면 초기 나무 (Pi가 꺼짐·네트워크 끊김)
        assert eco(client) == {"state": "initial"}
        send(client, GOOD)   # 다시 보내면 돌아온다
        assert eco(client)["state"] == "positive"


def test_clock_skew_warns_once(tmp_path, caplog):
    client, _ = make(tmp_path)
    late = {**GOOD, "observed_at": "2026-10-13T08:00:00+09:00",
            "window_start": "2026-10-13T06:00:00+09:00", "window_end": "2026-10-13T08:00:00+09:00"}
    with client, caplog.at_level(logging.WARNING):
        send(client, late)
        send(client, late)
        assert sum("clock differs" in r.message for r in caplog.records) == 1
        send(client, GOOD)        # 맞춰지면 다시 어긋날 때 또 알린다
        send(client, late)
        assert sum("clock differs" in r.message for r in caplog.records) == 2
        assert eco(client)["state"] == "positive"   # 판정은 그대로


@pytest.mark.parametrize("change, message", [
    ({"schema_version": 2}, "schema_version"),
    ({"schema_version": True}, "schema_version"),
    ({"extra": 1}, "unknown: extra"),
    ({"observed_at": "2026-10-13 09:00"}, "ISO 8601"),
    ({"observed_at": "2026-10-13T09:00:00"}, "time zone"),
    ({"observed_at": "2026-02-30T09:00:00+09:00"}, "not a real"),
    ({"window_start": "2026-10-13T10:00:00+09:00"}, "in order"),
    ({"window_end": "2026-10-13T10:00:00+09:00"}, "in order"),
    ({"verified_correct_count": 21}, "cannot exceed"),
    ({"verified_correct_count": -1}, "whole number"),
    ({"verified_total_count": 20.5}, "whole number"),
    ({"verified_total_count": True}, "whole number"),
    ({"verified_correct_count": None}, "both"),
    ({"source": ""}, "source"),
    ({"quality": 1}, "quality"),
])
def test_validate_rejects(change, message):
    with pytest.raises(EcoError, match=message):
        validate({**GOOD, **change})


def test_missing_field_rejected():
    body = dict(GOOD)
    del body["quality"]
    with pytest.raises(EcoError, match="missing: quality"):
        validate(body)


def test_bad_request_keeps_last_good(tmp_path):
    client, _ = make(tmp_path)
    with client:
        send(client, GOOD)
        response = send(client, {**GOOD, "verified_correct_count": 99})
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_payload"
        assert eco(client)["state"] == "positive"
        assert client.post("/api/v1/eco", content=b"{", headers={"Authorization": f"Bearer {TOKEN}",
                                                                   "Content-Type": "application/json"}).status_code == 400
        assert eco(client)["state"] == "positive"


def test_token(tmp_path):
    client, _ = make(tmp_path)
    with client:
        for token in (None, "wrong-token-0123456789"):
            response = send(client, GOOD, token=token)
            assert response.status_code == 401 and response.headers["www-authenticate"] == "Bearer"
        assert eco(client) == {"state": "initial"}


def test_robot_token_does_not_open_eco(tmp_path):
    clock = Clock()
    s = Settings(map_yaml=write_map(tmp_path), visitor_enabled=True)
    app = create_app(s, Store(s, clock, lambda: "2026-10-13T00:00:00Z"), robot_token="robot-token-0123456789", eco_token=TOKEN)
    with TestClient(app) as client:
        assert send(client, GOOD, token="robot-token-0123456789").status_code == 401
        assert send(client, GOOD).status_code == 200


def test_thresholds_from_settings(tmp_path):
    client, _ = make(tmp_path, eco_positive_percent=95, eco_min_samples=5, eco_max_age_s=60)
    with client:
        send(client, {**GOOD, "verified_correct_count": 4, "verified_total_count": 5})
        assert eco(client)["state"] == "negative" and eco(client)["total"] == 5


def test_judge_none_is_initial():
    assert judge(None, 80, 20) == {"state": "initial"}


def test_load_eco_token(tmp_path):
    base = Settings()
    assert load_eco_token(base, {"ECO_TOKEN": TOKEN}) == (True, TOKEN)
    # 토큰이 없으면 끈다 (선택 기능이라 서버는 뜬다). 로컬 개발(allow_no_robot_token)이면 토큰 없이 받는다
    assert load_eco_token(base, {}) == (False, None)
    assert load_eco_token(Settings(allow_no_robot_token=True), {}) == (True, None)
    path = tmp_path / "eco_token"
    path.write_text(TOKEN + "\n")
    assert load_eco_token(Settings(eco_token_file=str(path)), {}) == (True, TOKEN)
    with pytest.raises(RuntimeError, match="at least"):
        load_eco_token(base, {"ECO_TOKEN": "short"})
    with pytest.raises(RuntimeError, match="differ"):
        load_eco_token(base, {"ECO_TOKEN": TOKEN, "ROBOT_TOKEN": TOKEN})


def test_eco_off_without_token(tmp_path, monkeypatch):
    # 운영 경로(설정 파일)에서 ECO_TOKEN이 없으면 404
    config = tmp_path / "config.json"
    config.write_text(Settings(map_yaml=write_map(tmp_path), visitor_enabled=True, allow_no_login=True).model_dump_json())
    monkeypatch.setenv("DASHBOARD_CONFIG", str(config))
    monkeypatch.setenv("ROBOT_TOKEN", "robot-token-0123456789")
    monkeypatch.delenv("ECO_TOKEN", raising=False)
    with TestClient(create_app()) as client:
        response = send(client, GOOD)
        assert response.status_code == 404 and response.json()["error"]["code"] == "eco_not_configured"
        assert eco(client) == {"state": "initial"}


def test_display_eco_switch():
    base = {"version": 1, "schedule": []}
    assert validate_display(base)["eco"] == {"enabled": True}
    assert validate_display({**base, "eco": {"enabled": False}})["eco"] == {"enabled": False}
    assert validate_display({**base, "timing": {"eco_s": 20}})["timing"]["eco_s"] == 20
    for bad in ({"enabled": "yes"}, {"on": True}, []):
        with pytest.raises(DisplayError, match="eco must"):
            validate_display({**base, "eco": bad})
