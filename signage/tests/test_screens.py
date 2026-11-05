"""화면 값(view)과 그리기: PRD 9절 시나리오 4~6, 12, 13, 15 / FR-03, FR-04, FR-13, FR-17."""

import os
import shutil

import pytest
from PySide6.QtGui import QImage, QPainter

from app.config import APP_DEFAULTS, deep_merge
from app.content_loader import ContentStore, FontBook
from app.context import AppContext
from app.data_manager import Clock, DataManager
from app.renderer.stage import Stage
from app.screens import build_screens
from app.util import atomic_write_json
from conftest import TZ


def make_ctx(project, **overrides):
    cfg = deep_merge(APP_DEFAULTS, overrides)
    clock = Clock(TZ)
    data = DataManager(cfg, project, clock)
    data.poll_all_once()
    ctx = AppContext(project, project / "config/app.yaml", cfg, clock, data, ContentStore(project),
                     FontBook(project, cfg["theme"]))
    return ctx, build_screens(ctx)


def bump(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def write_bins(project, general, recycling, clock):
    def entry(v):
        if v is None:
            return {"fill_percent": None, "measurement_method": "unknown", "quality": "unavailable"}
        return {"fill_percent": v, "measurement_method": "weight_estimate", "quality": "ok"}

    atomic_write_json(project / "data/bin_status.json", {
        "schema_version": 1, "observed_at": clock.now().isoformat(), "source": "test",
        "bins": {"general": entry(general), "recycling": entry(recycling)}})


def test_bin_view_mock_demo(qapp, project):  # 시나리오 4
    ctx, screens = make_ctx(project, app={"mode": "demo"}, bin_status={"adapter": "mock"})
    v = screens["bin_status"].build_view(ctx.clock.now())
    assert v["mock"] and ctx.demo
    assert v["bins"]["general"]["text"] == "60%" and v["bins"]["general"]["fill"] == pytest.approx(0.6)
    assert v["bins"]["recycling"]["text"] == "10%" and v["bins"]["recycling"]["fill"] == pytest.approx(0.1)


def test_bin_view_production_null_and_partial(qapp, project):  # 시나리오 5, 6
    ctx, screens = make_ctx(project)
    v = screens["bin_status"].build_view(ctx.clock.now())
    for b in v["bins"].values():
        assert b["text"] == "정보 없음" and b["fill"] is None
    write_bins(project, 60, None, ctx.clock)
    ctx.data.poll_bins()
    v = screens["bin_status"].build_view(ctx.clock.now())
    assert v["bins"]["general"]["text"] == "60%"
    assert v["bins"]["recycling"]["text"] == "정보 없음" and not v["mock"]


def test_text_file_replacement_changes_label(qapp, project):  # FR-03
    ctx, screens = make_ctx(project)
    label = project / "content/text/bin_general_label.txt"
    label.write_text("일반쓰레기\n", encoding="utf-8")
    bump(label)
    ctx.content.refresh()
    assert screens["bin_status"].build_view(ctx.clock.now())["bins"]["general"]["label"] == "일반쓰레기"


def write_eco(project, correct, total, clock):
    from datetime import timedelta
    now = clock.now()
    atomic_write_json(project / "data/eco_metrics.json", {
        "schema_version": 1, "observed_at": now.isoformat(), "window_start": (now - timedelta(hours=24)).isoformat(),
        "window_end": now.isoformat(), "source": "test", "evaluation_method": "human_audit",
        "verified_correct_count": correct, "verified_total_count": total, "quality": "ok"})


def test_eco_bundle_swap_and_damaged_image(qapp, project):  # 시나리오 12, 15
    ctx, screens = make_ctx(project)
    eco = screens["eco_feedback"]
    v = eco.build_view(ctx.clock.now())
    assert v["state"] == "initial" and v["pending"] == "평가 준비 중"
    assert v["text"].startswith("여러분의 재활용이") and v["image"] is not None

    write_eco(project, 18, 20, ctx.clock)
    ctx.data.poll_eco()
    v = eco.build_view(ctx.clock.now())
    assert v["state"] == "positive" and v["pending"] == "" and v["text"].startswith("분리수거가 잘 되고")
    old_key = v["image"].cacheKey()

    # 문구와 그림을 같이 교체 → 새 묶음
    txt, png = project / "content/text/eco_positive.txt", project / "assets/images/tree_positive.png"
    txt.write_text("고마워요!\n", encoding="utf-8")
    shutil.copy(project / "assets/images/tree_initial.png", png)
    bump(txt), bump(png)
    ctx.content.refresh()
    v = eco.build_view(ctx.clock.now())
    assert v["text"] == "고마워요!" and v["image"].cacheKey() != old_key
    good_key = v["image"].cacheKey()

    # 문구는 바뀌었는데 그림이 깨짐 → 반쪽만 바뀌지 않고 마지막 정상 묶음 유지
    txt.write_text("반쪽 교체\n", encoding="utf-8")
    png.write_bytes(b"\x89PNG broken")
    bump(txt), bump(png)
    ctx.content.refresh()
    v = eco.build_view(ctx.clock.now())
    assert v["text"] == "고마워요!" and v["image"].cacheKey() == good_key


def test_eco_missing_files_fall_back_to_default_bundle(qapp, project):
    (project / "content/text/eco_negative.txt").unlink()
    ctx, screens = make_ctx(project)
    write_eco(project, 10, 20, ctx.clock)
    ctx.data.poll_eco()
    v = screens["eco_feedback"].build_view(ctx.clock.now())
    assert v["state"] == "negative" and v["text"].startswith("분리수거가 잘 안되고") and v["image"] is None


def test_schedule_empty_text(qapp, project):  # 시나리오 3
    ctx, screens = make_ctx(project)
    v = screens["clock_schedule"].build_view(ctx.clock.now())
    assert v["lines"] == [] and v["empty_text"] == "예정된 행사가 없습니다."


def test_content_path_outside_project_is_rejected(qapp, project):
    store = ContentStore(project)
    assert store.text("../../etc/passwd", "기본") == "기본"


@pytest.mark.parametrize("mode", ["production", "demo"])
def test_all_screens_render_1920x1080(qapp, project, mode):  # 시나리오 13
    ctx, screens = make_ctx(project, app={"mode": mode})
    stage = Stage(ctx, screens)
    for s in screens.values():
        img = QImage(1920, 1080, QImage.Format.Format_RGB32)
        p = QPainter(img)
        stage.render_scene(p, s, ctx.clock.now())
        p.end()
        assert img.pixelColor(5, 5).name() == "#ffffff"  # 배경
    stage.deleteLater()


def test_broken_screen_yaml_and_paint_error_do_not_crash(qapp, project):  # 시나리오 15
    (project / "config/screens/bin_status.yaml").write_text("boxes: [이건 잘못된", encoding="utf-8")
    ctx, screens = make_ctx(project)
    stage = Stage(ctx, screens)
    assert screens["bin_status"].cfg["boxes"]["general"]["rect"]  # 기본 배치로 대체

    def boom(p, now):
        raise RuntimeError("화면 오류")

    screens["eco_feedback"].paint = boom
    img = QImage(1920, 1080, QImage.Format.Format_RGB32)
    p = QPainter(img)
    stage.render_scene(p, screens["eco_feedback"], ctx.clock.now())  # 예외가 밖으로 나오지 않음
    p.end()
    stage.next_screen()
    stage.deleteLater()
