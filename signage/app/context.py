"""화면들이 같이 쓰는 객체 묶음과 설정 자동 재로딩."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, load_app_config, load_screen_config
from .content_loader import ContentStore, FontBook
from .data_manager import Clock, DataManager
from .renderer.draw import ImagePainter, TextFitter
from .util import file_signature

log = logging.getLogger("signage")

# 실행 중 바꿔도 반영되는 app.yaml 항목. 나머지(데이터 공급원, mode 등)는 재시작해야 반영된다.
LIVE_SECTIONS = ("rotation", "theme", "content")


@dataclass
class AppContext:
    root: Path
    config_path: Path
    cfg: dict
    clock: Clock
    data: DataManager
    content: ContentStore
    fonts: FontBook
    text: TextFitter = field(init=False)
    images: ImagePainter = field(init=False)
    _sigs: dict = field(default_factory=dict)

    def __post_init__(self):
        self.text = TextFitter(self.fonts)
        self.images = ImagePainter()
        self._sigs = self._config_signatures()

    @property
    def theme(self) -> dict:
        return self.cfg["theme"]

    @property
    def demo(self) -> bool:
        return self.cfg["app"]["mode"] == "demo"

    def screen_config(self, screen_id: str, defaults: dict) -> dict:
        try:
            return load_screen_config(self.root, screen_id, defaults)
        except Exception as e:
            log.error("화면 설정 %s.yaml 오류: %s → 기본 배치 사용", screen_id, e)
            return defaults

    # ------------------------------------------------------------ 자동 재로딩

    def _config_signatures(self) -> dict:
        files = [self.config_path, *sorted((self.root / "config" / "screens").glob("*.yaml"))]
        return {str(f): file_signature(f) for f in files}

    def config_changed(self) -> tuple[bool, set[str]]:
        """(app.yaml 바뀜, 바뀐 화면 id들). 확인한 시점의 서명을 기억한다."""
        new = self._config_signatures()
        changed = {k for k in set(new) | set(self._sigs) if new.get(k) != self._sigs.get(k)}
        self._sigs = new
        app_changed = str(self.config_path) in changed
        screens = {Path(k).stem for k in changed if k != str(self.config_path)}
        return app_changed, screens

    def reload_app_config(self) -> bool:
        try:
            new = load_app_config(self.config_path)
        except (ConfigError, OSError, Exception) as e:
            log.error("app.yaml 다시 읽기 실패: %s → 이전 설정 유지", e)
            return False
        # 시작할 때 명령행으로 바꾼 mode 등은 유지하고, 실행 중 반영 가능한 항목만 갈아 끼운다
        restart_needed = [k for k in new if k not in LIVE_SECTIONS and new[k] != self.cfg.get(k)
                          and k not in ("app", "display")]
        for key in LIVE_SECTIONS:
            self.cfg[key] = new[key]
        self.fonts.configure(self.cfg["theme"])
        log.info("app.yaml 반영: %s", ", ".join(LIVE_SECTIONS))
        if restart_needed:
            log.warning("다음 항목은 재시작해야 반영됩니다: %s", ", ".join(restart_needed))
        return True
