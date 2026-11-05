"""PRD 5.3/5.4 계약과 9절 시나리오 4~11."""

import json
from datetime import timedelta

import pytest

from app.adapters import build_bin_adapter, build_eco_adapter
from app.adapters.base import AdapterError, UnavailableAdapter
from app.adapters.json_file import JsonFileAdapter
from app.adapters.mock import MockBinStatusAdapter, MockEcoMetricsAdapter
from app.bin_resolver import resolve_bins
from app.config import APP_DEFAULTS, deep_merge
from app.data_manager import Clock, DataManager
from app.eco_state_resolver import EcoPolicy, resolve_eco
from app.util import atomic_write_json
from conftest import TZ, kst

NOW = kst(2026, 11, 7, 14, 0)


def bins(general=None, recycling=None, observed=NOW, method="volume_estimate", **extra):
    def entry(v):
        if v is None:
            return {"fill_percent": None, "measurement_method": "unknown", "quality": "unavailable"}
        return {"fill_percent": v, "measurement_method": method, "quality": "ok"}

    snap = {"schema_version": 1, "observed_at": observed.isoformat() if observed else None, "source": "test",
            "bins": {"general": entry(general), "recycling": entry(recycling)}}
    snap.update(extra)
    return snap


def view(snap, now=NOW, ttl=120):
    return resolve_bins(snap, now, ttl, TZ)


# ---------------------------------------------------------------- 적재율

def test_bins_mock_values_in_demo():  # 시나리오 4
    cfg = deep_merge(APP_DEFAULTS, {"app": {"mode": "demo"}, "bin_status": {"adapter": "mock"}})
    adapter = build_bin_adapter(cfg, ROOT_UNUSED, TZ, lambda: NOW)
    assert isinstance(adapter, MockBinStatusAdapter) and adapter.is_mock
    v = resolve_bins(adapter.read(), NOW, 120, TZ, adapter.is_mock)
    assert v.readings["general"].percent == 60 and v.readings["recycling"].percent == 10 and v.is_mock


def test_mock_is_refused_in_production():  # FR-14
    cfg = deep_merge(APP_DEFAULTS, {"bin_status": {"adapter": "mock"}, "eco_feedback": {"adapter": "mock"}})
    assert isinstance(build_bin_adapter(cfg, ROOT_UNUSED, TZ), UnavailableAdapter)
    assert isinstance(build_eco_adapter(cfg, ROOT_UNUSED, TZ), UnavailableAdapter)


def test_bins_null_values_unavailable_not_zero():  # 시나리오 5
    v = view(bins(None, None))
    assert not v.readings["general"].available and v.readings["general"].percent is None
    assert not v.readings["recycling"].available
    assert not any(r.available for r in view(None).readings.values())


def test_bins_partial_failure_isolated():  # 시나리오 6
    v = view(bins(60, None))
    assert v.readings["general"].available and v.readings["general"].percent == 60
    assert not v.readings["recycling"].available


def test_bins_expire_after_ttl():  # 시나리오 7
    snap = bins(60, 10, observed=NOW)
    assert view(snap, NOW + timedelta(seconds=120)).readings["general"].available
    assert not view(snap, NOW + timedelta(seconds=121)).readings["general"].available


def test_bins_exact_zero_is_shown_as_zero():
    r = view(bins(0, 100)).readings
    assert r["general"].available and r["general"].percent == 0.0
    assert r["recycling"].percent == 100.0


@pytest.mark.parametrize("bad", [True, -1, 100.5, "60", float("nan")])
def test_bins_invalid_percent_unavailable(bad):
    assert not view(bins(bad, 10)).readings["general"].available


def test_bins_unknown_method_or_bad_schema_or_future_unavailable():
    assert not view(bins(60, 10, method="unknown")).readings["general"].available
    assert not view(bins(60, 10, schema_version=2)).readings["general"].available
    assert not view(bins(60, 10, observed=NOW + timedelta(minutes=5))).readings["general"].available
    assert view(bins(60, 10, observed=NOW + timedelta(seconds=10))).readings["general"].available  # 시계 오차


def test_bins_naive_and_z_timestamps():
    snap = bins(60, 10)
    snap["observed_at"] = "2026-11-07T05:00:00Z"  # = 14:00 KST
    assert view(snap).readings["general"].available
    snap["observed_at"] = "2026-11-07T14:00:00"  # 시간대 없으면 Asia/Seoul
    assert view(snap).readings["general"].available


# ---------------------------------------------------------------- 성공률

POLICY = EcoPolicy()


def eco(correct, total, method="human_audit", observed=NOW, window_hours=24, **extra):
    m = {"schema_version": 1, "observed_at": observed.isoformat(),
         "window_start": (observed - timedelta(hours=window_hours)).isoformat(),
         "window_end": observed.isoformat(), "source": "test", "evaluation_method": method,
         "verified_correct_count": correct, "verified_total_count": total, "quality": "ok"}
    m.update(extra)
    return m


def test_eco_positive_18_of_20():  # 시나리오 8
    r = resolve_eco(eco(18, 20), NOW, POLICY, TZ)
    assert r.state == "positive" and r.evaluated and r.rate_percent == 90


def test_eco_negative_14_of_20():  # 시나리오 9
    r = resolve_eco(eco(14, 20), NOW, POLICY, TZ)
    assert r.state == "negative" and r.rate_percent == 70


def test_eco_threshold_boundary_is_positive():
    assert resolve_eco(eco(16, 20), NOW, POLICY, TZ).state == "positive"  # 정확히 80%


def test_eco_insufficient_samples_initial_pending():  # 시나리오 10
    r = resolve_eco(eco(9, 10), NOW, POLICY, TZ)
    assert r.state == "initial" and not r.evaluated and "표본 부족" in r.reason


def test_eco_prediction_only_not_evaluated():  # 시나리오 11
    m = eco(None, None, method="unknown")
    m["predicted_class_counts"] = {"plastic": 30}
    r = resolve_eco(m, NOW, POLICY, TZ)
    assert r.state == "initial" and not r.evaluated


@pytest.mark.parametrize("metrics,reason", [
    (None, "데이터 없음"),
    (eco(18, 20, method="model_prediction"), "검증 근거"),
    (eco(0, 0), "판정 불가"),
    (eco(21, 20), ">"),
    (eco(18.0, 20), "정수"),
    (eco(True, 20), "정수"),
    (eco(18, 20, quality="error"), "quality"),
    (eco(18, 20, observed=NOW - timedelta(seconds=601)), "만료"),
    (eco(18, 20, window_hours=48), "평가 창"),
    (eco(18, 20, window_start=None), "window"),
])
def test_eco_not_evaluated_cases(metrics, reason):
    r = resolve_eco(metrics, NOW, POLICY, TZ)
    assert r.state == "initial" and not r.evaluated and reason in r.reason


def test_eco_mock_cycles_scenarios():
    clock = [0.0]
    a = MockEcoMetricsAdapter([{"verified_correct_count": 18, "verified_total_count": 20},
                               {"verified_correct_count": 14, "verified_total_count": 20}], 10, TZ,
                              now_fn=lambda: NOW)
    a._cycle._clock = lambda: clock[0]
    a._cycle._t0 = 0.0
    assert resolve_eco(a.read(), NOW, POLICY, TZ).state == "positive"
    clock[0] = 10.5
    assert resolve_eco(a.read(), NOW, POLICY, TZ).state == "negative"


# ---------------------------------------------------------------- JSON 파일 / DataManager

def test_json_adapter_errors(tmp_path):
    p = tmp_path / "x.json"
    with pytest.raises(AdapterError):
        JsonFileAdapter(p).read()
    p.write_text("{broken", encoding="utf-8")
    with pytest.raises(AdapterError):
        JsonFileAdapter(p, retry_delay=0).read()
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(AdapterError):
        JsonFileAdapter(p).read()


def test_atomic_write_roundtrip(tmp_path):
    p = tmp_path / "sub/out.json"
    atomic_write_json(p, {"a": "한글"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": "한글"}
    assert [f.name for f in p.parent.iterdir()] == ["out.json"]  # 임시 파일이 남지 않음


def test_datamanager_keeps_last_value_only_until_ttl(project):
    path = project / "data/bin_status.json"
    clock = Clock(TZ)
    now = clock.now()
    atomic_write_json(path, bins(60, 10, observed=now))
    cfg = deep_merge(APP_DEFAULTS, {})
    dm = DataManager(cfg, project, clock)
    dm.poll_bins()
    assert dm.bin_view(now).readings["general"].percent == 60

    path.write_text("{ 쓰는 중", encoding="utf-8")  # 깨진 파일: 마지막 값 유지
    dm.poll_bins()
    assert dm.bin_view(now).readings["general"].percent == 60
    # 그러나 유효기간이 지나면 '정보 없음'
    assert not dm.bin_view(now + timedelta(seconds=121)).readings["general"].available


def test_shipped_data_files_show_unavailable_and_initial(project):
    dm = DataManager(deep_merge(APP_DEFAULTS, {}), project, Clock(TZ))
    dm.poll_all_once()
    assert not any(r.available for r in dm.bin_view().readings.values())
    r = dm.eco_result()
    assert r.state == "initial" and not r.evaluated


ROOT_UNUSED = None  # mock/거부 경로는 루트를 쓰지 않는다
