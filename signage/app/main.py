"""진입점: python -m app.main [옵션]  (signage/ 디렉터리에서 실행)

  --demo / --production   app.yaml의 app.mode를 이번 실행만 바꾼다
  --mock                  --demo + 적재율·환경평가를 mock 값으로 (PC 미리보기)
  --windowed / --fullscreen
  --screen ID             한 화면만 고정 표시 (clock_schedule | bin_status | eco_feedback)
  --at 2026-11-07T13:30   이 시각부터 시작한 것처럼 동작 (일정 시험용, 시간은 계속 흐름)
  --screenshot DIR        세 화면을 1920×1080 PNG로 저장하고 끝낸다 (창 없이도 됨)
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import signal
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import PROJECT_ROOT
from .config import SCREEN_IDS, ConfigError, load_app_config, resolve_path

log = logging.getLogger("signage")


def setup_logging(cfg: dict, root: Path) -> None:
    lc = cfg["logging"]
    logger = logging.getLogger("signage")
    logger.setLevel(getattr(logging, str(lc.get("level", "INFO")).upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    if lc.get("file"):
        try:
            path = resolve_path(root, lc["file"])
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(path, maxBytes=int(lc["max_bytes"]),
                                                      backupCount=int(lc["backup_count"]), encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except (OSError, ConfigError) as e:
            logger.warning("로그 파일을 쓸 수 없어 화면 출력만 합니다: %s", e)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="signage", description="Automaton 로봇 하단 디스플레이")
    ap.add_argument("--config", default="config/app.yaml", help="app.yaml 경로 (signage/ 기준)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="시연 모드 (Mock 허용, DEMO 표시)")
    mode.add_argument("--production", action="store_true", help="운영 모드")
    mode.add_argument("--mock", action="store_true",
                      help="시연 모드 + 적재율·환경평가를 mock 공급원으로 (PC 미리보기용)")
    win = ap.add_mutually_exclusive_group()
    win.add_argument("--windowed", action="store_true", help="창 모드 (PC 미리보기)")
    win.add_argument("--fullscreen", action="store_true", help="전체화면")
    ap.add_argument("--screen", choices=SCREEN_IDS, help="한 화면만 고정 표시")
    ap.add_argument("--at", help="시작 시각 (ISO 8601, 예: 2026-11-07T13:30)")
    ap.add_argument("--screenshot", metavar="DIR", help="화면을 PNG로 저장하고 종료")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = PROJECT_ROOT
    config_path = (root / args.config).resolve() if not Path(args.config).is_absolute() else Path(args.config)
    try:
        cfg = load_app_config(config_path)
    except (ConfigError, OSError) as e:
        print(f"설정 오류: {e}", file=sys.stderr)
        return 2
    if args.demo or args.mock:
        cfg["app"]["mode"] = "demo"
    if args.mock:
        cfg["bin_status"]["adapter"] = "mock"
        cfg["eco_feedback"]["adapter"] = "mock"
    elif args.production:
        cfg["app"]["mode"] = "production"
    if args.windowed:
        cfg["display"]["fullscreen"] = False
    elif args.fullscreen:
        cfg["display"]["fullscreen"] = True

    setup_logging(cfg, root)
    try:
        tz = ZoneInfo(cfg["app"]["timezone"])
    except Exception as e:
        log.error("시간대 %r 오류 (%s) → Asia/Seoul 사용", cfg["app"]["timezone"], e)
        tz = ZoneInfo("Asia/Seoul")
    start_at = None
    if args.at:
        try:
            start_at = datetime.fromisoformat(args.at)
        except ValueError:
            print(f"--at 형식 오류: {args.at}", file=sys.stderr)
            return 2

    # Qt는 설정·로그 준비 뒤에 import (설정 오류는 Qt 없이도 보이게)
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from .content_loader import ContentStore, FontBook
    from .context import AppContext
    from .data_manager import Clock, DataManager
    from .renderer.stage import Stage
    from .screens import build_screens

    app = QApplication(sys.argv[:1])
    app.setApplicationName("automaton-signage")
    clock = Clock(tz, start_at)
    log.info("시작: mode=%s, 시간대=%s, 현재=%s", cfg["app"]["mode"], tz, clock.now().isoformat(timespec="seconds"))
    data = DataManager(cfg, root, clock)
    ctx = AppContext(root, config_path, cfg, clock, data, ContentStore(root), FontBook(root, cfg["theme"]))
    screens = build_screens(ctx)
    stage = Stage(ctx, screens, pinned=args.screen)

    if args.screenshot:
        data.poll_all_once()
        out = Path(args.screenshot)
        out.mkdir(parents=True, exist_ok=True)
        ids = [args.screen] if args.screen else [r["id"] for r in stage.rotation]
        for sid in ids:
            img = QImage(stage.design_w, stage.design_h, QImage.Format.Format_RGB32)
            p = QPainter(img)
            stage.render_scene(p, screens[sid], clock.now())
            p.end()
            path = out / f"{sid}.png"
            img.save(str(path))
            log.info("저장: %s", path)
        return 0

    data.poll_all_once()  # 첫 화면부터 값이 보이게
    data.start()
    if cfg["display"]["fullscreen"]:
        stage.showFullScreen()
    else:
        w, h = cfg["display"].get("window_size", [960, 540])
        stage.resize(int(w), int(h))
        stage.show()

    # Ctrl+C / systemctl stop(SIGTERM)으로 깔끔하게 끝내기
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)  # 파이썬 시그널 처리기가 돌 기회를 준다
    keepalive.start(250)

    code = app.exec()
    data.stop()
    log.info("종료")
    return code


if __name__ == "__main__":
    sys.exit(main())
