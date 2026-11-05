"""외부 콘텐츠(문구 TXT, 이미지, 글꼴) 읽기와 자동 재로딩 (PRD 1절 원칙 1, FR-03/04/05/17).

- 파일이 바뀌면 refresh()에서 다시 읽는다 (수정시각·크기 비교).
- 새 파일이 깨졌거나 사라지면 마지막 정상값을 계속 쓴다. 한 번도 못 읽었으면 호출 측 기본값.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont, QFontDatabase, QImage

from .config import ConfigError, resolve_path
from .util import ChangeLogger, file_signature

log = logging.getLogger("signage.content")

MAX_TEXT_BYTES = 100_000
MAX_IMAGE_BYTES = 30_000_000
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")


@dataclass
class _Entry:
    kind: str  # "text" | "image"
    path: Path
    sig: tuple[int, int] | None = None
    value: Any = None  # 마지막 정상값
    ok: bool = False  # 가장 최근 시도가 성공했는지


class ContentStore:
    def __init__(self, root: Path):
        self.root = root
        self._entries: dict[str, _Entry] = {}
        self._changes = ChangeLogger(log)

    # ------------------------------------------------------------ 조회

    def text(self, rel: str | None, default: str = "") -> str:
        entry = self._entry("text", rel)
        return default if entry is None or entry.value is None else entry.value

    def image(self, rel: str | None) -> QImage | None:
        entry = self._entry("image", rel)
        return None if entry is None else entry.value

    def is_ok(self, rel: str | None) -> bool:
        """가장 최근 읽기가 성공했는지 (묶음 단위 원자적 교체 판단용)."""
        entry = self._entries.get(rel or "")
        return bool(entry and entry.ok and entry.value is not None)

    def _entry(self, kind: str, rel: str | None) -> _Entry | None:
        if not rel:
            return None
        entry = self._entries.get(rel)
        if entry is None:
            try:
                path = resolve_path(self.root, rel)
            except ConfigError as e:
                self._changes.log(f"path:{rel}", logging.ERROR, str(e))
                return None
            entry = _Entry(kind, path)
            self._entries[rel] = entry
            self._load(rel, entry)
        return entry

    # ------------------------------------------------------------ 갱신

    def refresh(self) -> None:
        for rel, entry in self._entries.items():
            if file_signature(entry.path) != entry.sig:
                self._load(rel, entry)

    def _load(self, rel: str, entry: _Entry) -> None:
        entry.sig = file_signature(entry.path)
        try:
            if entry.sig is None:
                raise OSError("파일 없음")
            value = self._read_text(entry.path) if entry.kind == "text" else self._read_image(entry.path)
        except Exception as e:
            entry.ok = False
            kept = "마지막 정상값 유지" if entry.value is not None else "기본값 사용"
            self._changes.log(f"load:{rel}", logging.WARNING, f"콘텐츠 읽기 실패 {rel}: {e} → {kept}")
            return
        changed = entry.value is not None
        entry.value, entry.ok = value, True
        self._changes.log(f"load:{rel}", logging.INFO, None)
        if changed:
            log.info("콘텐츠 갱신: %s", rel)

    @staticmethod
    def _read_text(path: Path) -> str:
        data = path.read_bytes()
        if len(data) > MAX_TEXT_BYTES:
            raise ValueError("텍스트 파일이 너무 큼")
        text = data.decode("utf-8-sig")  # BOM이 있어도 받는다
        return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")

    @staticmethod
    def _read_image(path: Path) -> QImage:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("이미지 파일이 너무 큼")
        img = QImage(str(path))
        if img.isNull():
            raise ValueError("이미지를 해석할 수 없음 (손상/지원하지 않는 형식)")
        return img


class FontBook:
    """assets/fonts의 글꼴을 등록하고, theme.font_families 중 설치된 첫 글꼴을 쓴다."""

    def __init__(self, root: Path, theme: dict):
        self.root = root
        self._cache: dict[tuple, QFont] = {}
        self._loaded_files: set[Path] = set()
        self.family = ""
        self.configure(theme)

    def configure(self, theme: dict) -> None:
        self._cache.clear()
        try:
            font_dir = resolve_path(self.root, theme.get("font_dir") or "assets/fonts")
        except ConfigError as e:
            log.error("%s", e)
            font_dir = None
        if font_dir and font_dir.is_dir():
            for f in sorted(font_dir.iterdir()):
                if f.suffix.lower() in FONT_SUFFIXES and f not in self._loaded_files:
                    fid = QFontDatabase.addApplicationFont(str(f))
                    if fid < 0:
                        log.warning("글꼴 등록 실패: %s", f.name)
                    else:
                        log.info("글꼴 등록: %s → %s", f.name, QFontDatabase.applicationFontFamilies(fid))
                    self._loaded_files.add(f)
        available = set(QFontDatabase.families())
        wanted = theme.get("font_families") or []
        self.family = next((fam for fam in wanted if fam in available), "")
        if self.family:
            log.info("글꼴: %s", self.family)
        else:
            log.warning("설정한 글꼴(%s)이 없어 시스템 기본 글꼴을 씁니다. 한글이 깨지면 assets/fonts에 "
                        "한글 글꼴을 넣으세요.", ", ".join(wanted))

    def font(self, spec: dict | None, size_px: int | None = None) -> QFont:
        spec = spec or {}
        family = spec.get("family") or self.family
        size = int(size_px or spec.get("size", 48))
        weight = spec.get("weight", "normal")
        key = (family, size, str(weight))
        f = self._cache.get(key)
        if f is None:
            f = QFont(family) if family else QFont()
            f.setPixelSize(max(1, size))
            if isinstance(weight, int):
                f.setWeight(QFont.Weight(weight))
            else:
                f.setWeight({"bold": QFont.Weight.Bold, "medium": QFont.Weight.Medium,
                             "light": QFont.Weight.Light}.get(str(weight), QFont.Weight.Normal))
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            self._cache[key] = f
        return f
