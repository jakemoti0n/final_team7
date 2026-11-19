"""방문자 안내 약도 파일(guide_yaml). 관제 화면의 약도 편집 페이지가 읽고 쓰고, 방문자 화면이 그린다.

좌표는 지도와 같은 미터 좌표(map 프레임)라서 로봇 위치를 약도 위에 바로 그릴 수 있다.
그릴 수 있는 영역(bounds)은 지도보다 넓어도 된다 (로봇이 가지 않는 방도 그리게).
지도 하나에 약도 하나. 저장은 문서 전체를 revision 검사 뒤 원자적 교체로 (waypoint와 같은 방식).

version: 1
map: real_open_space_20261111.yaml        # 어느 지도 좌표로 그렸는지 (다른 지도면 화면이 경고)
bounds: {x_min: -20, y_min: -20, x_max: 34, y_max: 28}
categories:                               # 구역 종류. 편집 화면에서 추가·수정
  - {key: classroom, label: 강의실, color: '#DCE8F5', icon: classroom}
areas:                                    # 다각형 구역 (꼭짓점 m)
  - {name: 201 강의실, category: classroom, polygon: [[0, 0], [6, 0], [6, 4], [0, 4]]}
markers:                                  # 점 표시 (입구·안내데스크 등)
  - {name: 정문, category: entrance, x: 0.2, y: -2.8}
"""
import copy
import hashlib
import math
from pathlib import Path
import re

import yaml

from .files import atomic_write

VERSION = 1
BOUNDS_MARGIN_M = 10.0      # 처음 만들 때 그릴 수 있는 영역: 지도 범위에서 사방으로 이만큼 넓힘
MAX_SPAN_M = 1000.0         # 그릴 수 있는 영역 한 변의 최대 길이
MAX_CATEGORIES = 50
MAX_AREAS = 300
MAX_MARKERS = 200
MAX_POINTS = 64             # 구역 하나의 꼭짓점 수
MAX_NAME = 32
MAX_BYTES = 256 * 1024      # 저장 요청 본문 상한 (구역 300 × 꼭짓점 64도 들어감)

# 화면에 내장된 아이콘 이름 (ui/src/features/guide/icons.tsx와 같게)
ICONS = ("none", "classroom", "event", "restroom", "entrance", "exit", "stairs", "elevator",
         "info", "food", "office", "medical", "restricted", "star")

DEFAULT_CATEGORIES = [
    dict(key="classroom", label="강의실", color="#DCE8F5", icon="classroom"),
    dict(key="event", label="행사장", color="#FCE9C8", icon="event"),
    dict(key="restroom", label="화장실", color="#DFF0E3", icon="restroom"),
    dict(key="entrance", label="입구", color="#FBE3E0", icon="entrance"),
    dict(key="corridor", label="복도", color="#F3F4F1", icon="none"),
    dict(key="stairs", label="계단·엘리베이터", color="#E8E3F4", icon="stairs"),
    dict(key="restricted", label="출입 금지", color="#E3E5E8", icon="restricted"),
    dict(key="other", label="기타", color="#FFFFFF", icon="none"),
]

KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")


class GuideError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def map_bounds(map_meta, margin=0.0):
    x0, y0 = map_meta["origin"][:2]
    return dict(x_min=round(x0 - margin, 3), y_min=round(y0 - margin, 3),
                x_max=round(x0 + map_meta["width"] * map_meta["resolution"] + margin, 3),
                y_max=round(y0 + map_meta["height"] * map_meta["resolution"] + margin, 3))


def empty_guide(map_meta, map_name):
    """파일이 아직 없을 때의 약도: 기본 종류, 지도보다 사방 10 m 넓은 영역, 구역 없음"""
    return dict(version=VERSION, map=map_name, bounds=map_bounds(map_meta, BOUNDS_MARGIN_M),
                categories=copy.deepcopy(DEFAULT_CATEGORIES), areas=[], markers=[])


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GuideError("invalid_guide", f"{what} must be a finite number")
    return round(float(value), 3)


def _text(value, what):
    if not isinstance(value, str):
        raise GuideError("invalid_guide", f"{what} must be text")
    value = value.strip()
    if not 1 <= len(value) <= MAX_NAME or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise GuideError("invalid_guide", f"{what} must be 1–{MAX_NAME} characters without control characters")
    return value


def _fields(item, required, what):
    if not isinstance(item, dict) or set(item) != set(required):
        raise GuideError("invalid_guide", f"{what} needs exactly: {', '.join(required)}")


def _segments_cross(p1, p2, q1, q2):
    """두 선분이 끝점이 아닌 곳에서 만나거나 겹치는가"""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

    def on(a, b, c):
        return min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9 and min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9

    o1, o2, o3, o4 = orient(p1, p2, q1), orient(p1, p2, q2), orient(q1, q2, p1), orient(q1, q2, p2)
    if o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4):
        return True
    return ((o1 == 0 and on(p1, p2, q1)) or (o2 == 0 and on(p1, p2, q2))
            or (o3 == 0 and on(q1, q2, p1)) or (o4 == 0 and on(q1, q2, p2)))


def _simple_polygon(points):
    """꼭짓점이 겹치지 않고, 변끼리 이웃한 변의 끝점 말고는 만나지 않으며, 넓이가 있는 다각형"""
    n = len(points)
    if len({tuple(p) for p in points}) != n:
        return False
    area = sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n)) / 2
    if abs(area) < 1e-6:
        return False
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue   # 이웃한 변은 끝점을 공유
            if _segments_cross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
                return False
    return True


def validate(guide):
    """화면이 보낸 약도를 검사해 정리된 사본을 돌려준다(이름 앞뒤 공백 제거, 좌표 mm 단위 반올림)"""
    _fields(guide, ("version", "map", "bounds", "categories", "areas", "markers"), "Guide")
    if guide["version"] != VERSION:
        raise GuideError("invalid_guide", f"version must be {VERSION}")
    if guide["map"] is not None and not isinstance(guide["map"], str):
        raise GuideError("invalid_guide", "map must be a file name or null")

    _fields(guide["bounds"], ("x_min", "y_min", "x_max", "y_max"), "bounds")
    b = {k: _number(v, f"bounds.{k}") for k, v in guide["bounds"].items()}
    if not (0 < b["x_max"] - b["x_min"] <= MAX_SPAN_M and 0 < b["y_max"] - b["y_min"] <= MAX_SPAN_M):
        raise GuideError("invalid_guide", f"bounds must have a positive size up to {MAX_SPAN_M:g} m")
    bounds = dict(x_min=b["x_min"], y_min=b["y_min"], x_max=b["x_max"], y_max=b["y_max"])

    def inside(x, y):
        return bounds["x_min"] <= x <= bounds["x_max"] and bounds["y_min"] <= y <= bounds["y_max"]

    if not isinstance(guide["categories"], list) or not 1 <= len(guide["categories"]) <= MAX_CATEGORIES:
        raise GuideError("invalid_guide", f"categories must be a list of 1–{MAX_CATEGORIES}")
    categories, keys = [], set()
    for c in guide["categories"]:
        _fields(c, ("key", "label", "color", "icon"), "Category")
        if not isinstance(c["key"], str) or not KEY_PATTERN.fullmatch(c["key"]) or c["key"] in keys:
            raise GuideError("invalid_guide", "Category key must be unique lowercase letters, digits, - or _ (1–32)")
        if not isinstance(c["color"], str) or not COLOR_PATTERN.fullmatch(c["color"]):
            raise GuideError("invalid_guide", "Category color must look like #A1B2C3")
        if c["icon"] not in ICONS:
            raise GuideError("invalid_guide", f"Category icon must be one of: {', '.join(ICONS)}")
        keys.add(c["key"])
        categories.append(dict(key=c["key"], label=_text(c["label"], "Category label"), color=c["color"].upper(), icon=c["icon"]))

    if not isinstance(guide["areas"], list) or len(guide["areas"]) > MAX_AREAS:
        raise GuideError("invalid_guide", f"areas must be a list of at most {MAX_AREAS}")
    areas = []
    for a in guide["areas"]:
        _fields(a, ("name", "category", "polygon"), "Area")
        name = _text(a["name"], "Area name")
        if a["category"] not in keys:
            raise GuideError("invalid_guide", f"Area {name}: unknown category")
        if not isinstance(a["polygon"], list) or not 3 <= len(a["polygon"]) <= MAX_POINTS:
            raise GuideError("invalid_guide", f"Area {name}: polygon needs 3–{MAX_POINTS} points")
        points = []
        for p in a["polygon"]:
            if not isinstance(p, list) or len(p) != 2:
                raise GuideError("invalid_guide", f"Area {name}: each point is [x, y]")
            x, y = _number(p[0], "x"), _number(p[1], "y")
            if not inside(x, y):
                raise GuideError("invalid_guide", f"Area {name}: points must be inside bounds")
            points.append([x, y])
        if not _simple_polygon(points):
            raise GuideError("invalid_guide", f"Area {name}: edges must not cross and the shape needs an area")
        areas.append(dict(name=name, category=a["category"], polygon=points))

    if not isinstance(guide["markers"], list) or len(guide["markers"]) > MAX_MARKERS:
        raise GuideError("invalid_guide", f"markers must be a list of at most {MAX_MARKERS}")
    markers = []
    for m in guide["markers"]:
        _fields(m, ("name", "category", "x", "y"), "Marker")
        name = _text(m["name"], "Marker name")
        if m["category"] not in keys:
            raise GuideError("invalid_guide", f"Marker {name}: unknown category")
        x, y = _number(m["x"], "x"), _number(m["y"], "y")
        if not inside(x, y):
            raise GuideError("invalid_guide", f"Marker {name}: position must be inside bounds")
        markers.append(dict(name=name, category=m["category"], x=x, y=y))

    return dict(version=VERSION, map=guide["map"], bounds=bounds, categories=categories, areas=areas, markers=markers)


class GuideFile:
    """약도 파일 하나. 파일이 없으면 빈 약도로 보이고 처음 저장할 때 만든다"""
    def __init__(self, path, map_meta, map_name):
        self.path = Path(path)
        self.map = map_meta
        self.map_name = map_name

    def read(self):
        """(약도, revision, 파일 있음). 파일이 없으면 revision은 빈 문자열"""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return empty_guide(self.map, self.map_name), "", False
        try:
            guide = validate(yaml.safe_load(raw))
        except yaml.YAMLError as exc:
            raise GuideError("invalid_guide_file", f"Guide file is not valid YAML: {exc}") from exc
        except GuideError as exc:
            raise GuideError("invalid_guide_file", f"Guide file is invalid: {exc}") from exc
        return guide, hashlib.sha256(raw).hexdigest(), True

    def document(self):
        guide, revision, exists = self.read()
        return dict(revision=revision, exists=exists, file=self.path.name, guide=guide,
                    map=self.map_name, map_matches=guide["map"] in (None, self.map_name),
                    map_bounds=map_bounds(self.map))

    def save(self, request):
        if not isinstance(request, dict) or set(request) != {"revision", "guide"} or not isinstance(request["revision"], str):
            raise GuideError("invalid_payload", "Send revision and guide")
        raw = self.raw()   # 파일이 깨져 있어도 덮어써서 고칠 수 있게 내용 검사 없이 revision만 본다
        revision = hashlib.sha256(raw).hexdigest() if raw is not None else ""
        if request["revision"] != revision:
            raise GuideError("revision_conflict", "Guide file changed; reload and try again")
        guide = validate(request["guide"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "# LIMBO 방문자 안내 약도 (관제 화면 '약도 편집'에서 저장). 좌표는 지도와 같은 m\n"
        body += yaml.safe_dump(guide, allow_unicode=True, sort_keys=False, default_flow_style=None, width=200)
        atomic_write(self.path, body.encode("utf-8"))
        return self.document()

    def raw(self):
        """내려받기용 파일 내용. 파일이 없으면 None"""
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None
