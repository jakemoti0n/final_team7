"""로봇 하단 디스플레이(/display)의 내용 폴더(display_dir). 운영자가 파일을 바꾸면 다음 요청에 반영된다.

폴더에 display.json 하나와 팜플렛 그림(PNG·JPEG·WebP), 「지나갑니다」 소리 파일(MP3·WAV·OGG, 선택)을 둔다. 로그인 없이 누구나 읽으므로 서버가 검사한다.
잘못 고친 파일이면 마지막 정상본을 계속 쓰고(로그에 이유), 처음부터 잘못됐으면 오류를 낸다.

{
  "version": 1,
  "message": "쓰레기는 LIMBO에게 주세요.",           # (선택) 장면 ① 아래 한 줄. null이면 없음
  "schedule": [                                       # 행사 일정. 화면이 지금 시각 기준으로 지난·지금·다음을 고른다
    {"date": "2026-11-27", "start": "14:00", "end": "14:30", "title": "개회", "place": "주행사장"}
  ],                                                  # date·end·place는 null 가능 (date가 null이면 매일)
  "slides": ["pamphlet-1.png"],                       # (선택) 장면 ② 팜플렛. 이 폴더의 그림 파일 이름, 보여 줄 순서
  "sound": "passing.mp3",                             # (선택) 장면 ④ 「LIMBO가 지나갑니다」 때 한 번 틀 소리 (TTS로 만든 파일)
  "timing": {"location_s": 40, ...}                   # (선택) 장면 길이(초). 빠진 것은 기본값 (TIMING_DEFAULTS)
}
"""
import hashlib
import json
import logging
import math
from pathlib import Path
import re

from .guide import GuideError, MAX_IMAGE_BYTES, IMAGE_TYPES, image_info

VERSION = 1
CONFIG_NAME = "display.json"
MAX_CONFIG_BYTES = 64 * 1024
MAX_EVENTS = 50
MAX_SLIDES = 20
MAX_TOTAL_SLIDE_BYTES = 50 * 1024 * 1024   # 정상본 그림을 메모리에 들고 있으므로 합계를 묶는다
MAX_TITLE = 40
MAX_MESSAGE = 80
SLIDE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.(png|jpg|jpeg|webp)")
SOUND_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.(mp3|wav|ogg)")
SOUND_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg"}
MAX_SOUND_BYTES = 2 * 1024 * 1024    # 한 문장이면 수십 KB
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

# 회전 규칙 R (PRD v0.3): ① 40 s → ② 30 s → ① 40 s → ③ 오늘 횟수 10 s, 신호 장면 ③ 10 s · ④ 8 s(같은 신호 60 s 쿨다운)
TIMING_DEFAULTS = dict(location_s=40, slides_s=30, count_s=10, trash_alert_s=10, passing_s=8, passing_cooldown_s=60)
TIMING_MAX_S = 600


class DisplayError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _bad(message):
    return DisplayError("invalid_display", message)


def _text(value, what, limit, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise _bad(f"{what} must be text")
    value = value.strip()
    if not 1 <= len(value) <= limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise _bad(f"{what} must be 1–{limit} characters without control characters")
    return value


def _pattern(value, pattern, what, example, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _bad(f"{what} must look like {example}")
    return value


def validate(config):
    """display.json을 검사해 정리된 사본(빠진 선택 항목 채움, 일정은 날짜·시작 순)을 돌려준다"""
    if not isinstance(config, dict):
        raise _bad("display.json must be an object")
    unknown = set(config) - {"version", "message", "schedule", "slides", "sound", "timing"}
    if unknown or not {"version", "schedule"} <= set(config):
        raise _bad("display.json needs version and schedule; optional: message, slides, sound, timing")
    if config["version"] != VERSION:
        raise _bad(f"version must be {VERSION}")
    message = _text(config.get("message"), "message", MAX_MESSAGE, optional=True)

    if not isinstance(config["schedule"], list) or len(config["schedule"]) > MAX_EVENTS:
        raise _bad(f"schedule must be a list of at most {MAX_EVENTS}")
    schedule = []
    for item in config["schedule"]:
        if not isinstance(item, dict) or not {"start", "title"} <= set(item) or set(item) - {"date", "start", "end", "title", "place"}:
            raise _bad("Each event needs start and title; optional: date, end, place")
        title = _text(item["title"], "Event title", MAX_TITLE)
        event = dict(date=_pattern(item.get("date"), DATE, f"{title}: date", "2026-11-27", optional=True),
                     start=_pattern(item["start"], TIME, f"{title}: start", "14:00"),
                     end=_pattern(item.get("end"), TIME, f"{title}: end", "14:30", optional=True),
                     title=title, place=_text(item.get("place"), f"{title}: place", MAX_TITLE, optional=True))
        if event["end"] is not None and event["end"] <= event["start"]:
            raise _bad(f"{title}: end must be after start")
        schedule.append(event)
    schedule.sort(key=lambda e: (e["date"] or "", e["start"]))

    slides = config.get("slides", [])
    if not isinstance(slides, list) or len(slides) > MAX_SLIDES:
        raise _bad(f"slides must be a list of at most {MAX_SLIDES} file names")
    for name in slides:
        if not isinstance(name, str) or not SLIDE_NAME.fullmatch(name):
            raise _bad("Slide names use letters, digits, '.', '_', '-' and end in .png, .jpg, .jpeg or .webp")
    if len(set(slides)) != len(slides):
        raise _bad("A slide is listed twice")

    sound = config.get("sound")
    if sound is not None and (not isinstance(sound, str) or not SOUND_NAME.fullmatch(sound)):
        raise _bad("The sound name uses letters, digits, '.', '_', '-' and ends in .mp3, .wav or .ogg")

    timing = config.get("timing", {})
    if not isinstance(timing, dict) or set(timing) - set(TIMING_DEFAULTS):
        raise _bad(f"timing may have: {', '.join(TIMING_DEFAULTS)}")
    merged = dict(TIMING_DEFAULTS)
    for key, value in timing.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= TIMING_MAX_S:
            raise _bad(f"timing.{key} must be 1–{TIMING_MAX_S} seconds")
        merged[key] = value
    return dict(message=message, schedule=schedule, slides=list(slides), sound=sound, timing=merged)


def sound_kind(data):
    """소리 파일의 실제 형식 (머리 부분으로). 모르는 형식이면 None"""
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    return None


class DisplayFolder:
    def __init__(self, path):
        self.path = Path(path)
        self._key = None
        self._error = None      # 지금 파일이 잘못됐으면 그 이유
        self._view = None       # 마지막 정상본 {revision, message, schedule, slides: [{file, width, height, type, url}], timing}
        self._files = {}        # 정상본이 쓰는 그림 이름 → 바이트 (파일을 잘못 바꿔도 정상본 그림을 그대로 내주게 들고 있는다)

    def _stat_key(self):
        """display.json과 폴더 안 그림들의 (이름, 수정시각, 크기). 그림만 바꿔 넣어도 다시 읽게"""
        items = []
        try:
            for item in sorted(self.path.iterdir()):
                if item.name == CONFIG_NAME or SLIDE_NAME.fullmatch(item.name) or SOUND_NAME.fullmatch(item.name):
                    stat = item.stat()
                    items.append((item.name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            return None
        return tuple(items)

    def _load(self):
        config_path = self.path / CONFIG_NAME
        try:
            if config_path.stat().st_size > MAX_CONFIG_BYTES:
                raise _bad(f"display.json must be at most {MAX_CONFIG_BYTES // 1024} KB")
            raw = config_path.read_bytes()
        except FileNotFoundError as exc:
            raise DisplayError("display_not_found", f"{config_path} does not exist") from exc
        try:
            config = validate(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeError, RecursionError) as exc:
            if isinstance(exc, DisplayError):
                raise
            raise _bad(f"display.json is not valid UTF-8 JSON: {exc}") from exc
        digest = hashlib.sha256(raw)
        slides, files = [], {}
        for name in config["slides"]:
            try:
                data = (self.path / name).read_bytes()
            except FileNotFoundError as exc:
                raise _bad(f"Slide {name} is listed but the file is missing") from exc
            if len(data) > MAX_IMAGE_BYTES:
                raise _bad(f"Slide {name} must be at most {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
            try:
                ext, width, height = image_info(data)
            except GuideError as exc:
                raise _bad(f"Slide {name}: {exc}") from exc
            # 확장자와 실제 형식이 다르면 브라우저가 nosniff로 거절하므로 미리 막는다
            if ext != {"jpeg": "jpg"}.get(name.rsplit(".", 1)[1], name.rsplit(".", 1)[1]):
                raise _bad(f"Slide {name}: file is actually {ext.upper()}")
            if sum(map(len, files.values())) + len(data) > MAX_TOTAL_SLIDE_BYTES:
                raise _bad(f"Slides together must be at most {MAX_TOTAL_SLIDE_BYTES // (1024 * 1024)} MB")
            version = hashlib.sha256(data).hexdigest()[:16]
            digest.update(name.encode() + b"\0" + version.encode())
            files[name] = data
            slides.append(dict(file=name, width=width, height=height, type=IMAGE_TYPES[ext],
                               url=f"/api/v1/display/slides/{name}?v={version}"))
        sound = None
        if config["sound"] is not None:
            name = config["sound"]
            try:
                data = (self.path / name).read_bytes()
            except FileNotFoundError as exc:
                raise _bad(f"Sound {name} is named but the file is missing") from exc
            if len(data) > MAX_SOUND_BYTES:
                raise _bad(f"Sound {name} must be at most {MAX_SOUND_BYTES // (1024 * 1024)} MB")
            kind = sound_kind(data)
            if kind != name.rsplit(".", 1)[1]:
                raise _bad(f"Sound {name}: file is not a {name.rsplit('.', 1)[1].upper()} file" + (f" (it is {kind.upper()})" if kind else ""))
            version = hashlib.sha256(data).hexdigest()[:16]
            digest.update(b"sound\0" + name.encode() + b"\0" + version.encode())
            files[name] = data
            sound = dict(file=name, type=SOUND_TYPES[kind], url=f"/api/v1/display/sound/{name}?v={version}")
        view = dict(revision=digest.hexdigest(), message=config["message"], schedule=config["schedule"],
                    slides=slides, sound=sound, timing=config["timing"])
        return view, files

    def view(self):
        """지금 보여 줄 내용. 파일이 잘못되면 마지막 정상본, 그것도 없으면 DisplayError"""
        key = self._stat_key()
        if key is None:
            raise DisplayError("display_not_found", f"{self.path} is not a readable folder")
        if key != self._key:
            self._key, self._error = key, None
            try:
                self._view, self._files = self._load()
            except DisplayError as exc:
                # 파일이 바뀔 때 한 번만 알린다 (화면이 자주 물어도 로그가 쌓이지 않게)
                logging.error("display content is invalid%s: %s",
                              ", keeping the last good one" if self._view is not None else "", exc)
                self._error = exc
        if self._view is None:
            raise self._error
        return self._view

    def slide(self, name):
        """(바이트, 형식) 또는 None. 지금 정상본에 들어 있는 그림만"""
        data = self._current(name) if SLIDE_NAME.fullmatch(name) else None
        if data is None:
            return None
        ext = name.rsplit(".", 1)[1]
        return data, IMAGE_TYPES[{"jpeg": "jpg"}.get(ext, ext)]

    def sound(self, name):
        """(바이트, 형식) 또는 None. 지금 정상본이 쓰는 소리만"""
        data = self._current(name) if SOUND_NAME.fullmatch(name) else None
        if data is None:
            return None
        return data, SOUND_TYPES[name.rsplit(".", 1)[1]]

    def _current(self, name):
        try:
            self.view()
        except DisplayError:
            return None
        return self._files.get(name)
