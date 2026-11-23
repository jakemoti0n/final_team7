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
image:                                    # (선택) 메인 약도를 그림 파일로. null이면 구역 그리기가 메인
  file: image-0123456789abcdef.png        # 약도 파일 옆 <이름>_files/ 폴더 (PUT /api/v1/guide/image로 올림)
  width: 1080                             # 그림 크기 (px)
  height: 960
  transform: [0.05, 0, -20, 0, -0.05, 28] # 그림 픽셀 (u, v) → 지도 (x, y): x = a·u + b·v + c, y = d·u + e·v + f
  points: []                              # 기준점으로 맞췄으면 그 짝 [{image: [u, v], map: [x, y]}] (다시 고칠 때 씀)
  show_areas: false                       # 그림 위에 그린 구역도 보일지
"""
import copy
import hashlib
import math
from pathlib import Path
import re
import struct

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
MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 약도 그림 파일 상한
MAX_IMAGE_SIDE = 12000               # 그림 한 변의 최대 픽셀
MAX_POINT_PAIRS = 20
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
IMAGE_NAME = re.compile(r"image-[0-9a-f]{16}\.(png|jpg|webp)")

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
                categories=copy.deepcopy(DEFAULT_CATEGORIES), areas=[], markers=[], image=None)


def image_info(data):
    """그림 파일의 (확장자, 가로, 세로). 머리 부분만 읽는다. 지원하지 않거나 잘린 파일이면 GuideError"""
    try:
        return _image_info(data)
    except (struct.error, IndexError) as exc:
        raise GuideError("invalid_image", "Image file is truncated or damaged") from exc


def _image_info(data):
    def bad(message="Image must be a PNG, JPEG or WebP file"):
        return GuideError("invalid_image", message)
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        ext = "png"
    elif data[:3] == b"\xff\xd8\xff":
        # SOF 표시(가로·세로가 든 조각)를 찾을 때까지 조각을 건너뛴다
        pos, size = 2, None
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                raise bad("JPEG file is damaged")
            marker = data[pos + 1]
            if marker == 0xFF:
                pos += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                size = (width, height)
                break
            pos += 2 + length
        if size is None:
            raise bad("JPEG size not found")
        (width, height), ext = size, "jpg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width, height = (struct.unpack("<H", data[26:28])[0] & 0x3FFF), (struct.unpack("<H", data[28:30])[0] & 0x3FFF)
        elif chunk == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        elif chunk == b"VP8X":
            width, height = int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
        else:
            raise bad("WebP header not recognized")
        ext = "webp"
    else:
        raise bad()
    if not (1 <= width <= MAX_IMAGE_SIDE and 1 <= height <= MAX_IMAGE_SIDE):
        raise bad(f"Image sides must be 1–{MAX_IMAGE_SIDE} px")
    return ext, width, height


def image_corners(image):
    """그림 네 모서리의 지도 좌표"""
    a, b, c, d, e, f = image["transform"]
    w, h = image["width"], image["height"]
    return [(a * u + b * v + c, d * u + e * v + f) for u, v in ((0, 0), (w, 0), (w, h), (0, h))]


def _polygon_area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2


def _contains(points, x, y):
    """점이 다각형 안에 있는가 (반직선 교차 수). 변 위의 점은 어느 쪽이든 될 수 있다"""
    inside = False
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def area_at(areas, x, y):
    """(x, y)가 들어 있는 구역의 이름. 겹치면 가장 작은 구역(행사장 안의 부스처럼 더 구체적인 곳), 없으면 None"""
    found = [(_polygon_area(a["polygon"]), a["name"]) for a in areas if _contains(a["polygon"], x, y)]
    return min(found)[1] if found else None


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


def _validate_image(image, inside):
    if image is None:
        return None
    _fields(image, ("file", "width", "height", "transform", "points", "show_areas"), "image")
    if not isinstance(image["file"], str) or not IMAGE_NAME.fullmatch(image["file"]):
        raise GuideError("invalid_guide", "image.file must be a name returned by the image upload")
    for side in ("width", "height"):
        if isinstance(image[side], bool) or not isinstance(image[side], int) or not 1 <= image[side] <= MAX_IMAGE_SIDE:
            raise GuideError("invalid_guide", f"image.{side} must be 1–{MAX_IMAGE_SIDE}")
    if not isinstance(image["transform"], list) or len(image["transform"]) != 6:
        raise GuideError("invalid_guide", "image.transform needs 6 numbers")
    transform = [float(_number_raw(v, "image.transform")) for v in image["transform"]]
    a, b, _, d, e, _ = transform
    if abs(a * e - b * d) < 1e-12:
        raise GuideError("invalid_guide", "image.transform must not flatten the image")
    if not isinstance(image["points"], list) or len(image["points"]) > MAX_POINT_PAIRS:
        raise GuideError("invalid_guide", f"image.points must be a list of at most {MAX_POINT_PAIRS}")
    points = []
    for pair in image["points"]:
        _fields(pair, ("image", "map"), "image point")
        if not all(isinstance(p, list) and len(p) == 2 for p in (pair["image"], pair["map"])):
            raise GuideError("invalid_guide", "image point needs image [u, v] and map [x, y]")
        points.append(dict(image=[_number(v, "image point") for v in pair["image"]], map=[_number(v, "image point") for v in pair["map"]]))
    if not isinstance(image["show_areas"], bool):
        raise GuideError("invalid_guide", "image.show_areas must be true or false")
    cleaned = dict(file=image["file"], width=image["width"], height=image["height"], transform=transform,
                   points=points, show_areas=image["show_areas"])
    if not all(inside(x, y) for x, y in image_corners(cleaned)):
        raise GuideError("invalid_guide", "The image must lie inside bounds; widen the bounds first")
    return cleaned


def _number_raw(value, what):
    """반올림하지 않는 수 (변환 행렬은 작은 값이라 mm 반올림하면 망가진다)"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GuideError("invalid_guide", f"{what} must be a finite number")
    return value


def validate(guide):
    """화면이 보낸 약도를 검사해 정리된 사본을 돌려준다(이름 앞뒤 공백 제거, 좌표 mm 단위 반올림).
    image 항목은 없어도 된다(예전 파일)"""
    if isinstance(guide, dict) and "image" not in guide:
        guide = {**guide, "image": None}
    _fields(guide, ("version", "map", "bounds", "categories", "areas", "markers", "image"), "Guide")
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

    image = _validate_image(guide["image"], lambda x, y: inside(round(x, 3), round(y, 3)))
    return dict(version=VERSION, map=guide["map"], bounds=bounds, categories=categories, areas=areas, markers=markers, image=image)


class GuideFile:
    """약도 파일 하나. 파일이 없으면 빈 약도로 보이고 처음 저장할 때 만든다"""
    def __init__(self, path, map_meta, map_name):
        self.path = Path(path)
        self.map = map_meta
        self.map_name = map_name
        self.files = self.path.parent / f"{self.path.stem}_files"   # 약도 그림 (guide.yaml → guide_files/)
        self._public = (None, None)   # (파일 상태, 방문자용 약도) — 방문자 화면이 3초마다 물으므로 파일이 바뀔 때만 다시 읽는다

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
        if guide["image"] is not None and not (self.files / guide["image"]["file"]).is_file():
            raise GuideError("invalid_guide", "The image file is missing; upload it again")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "# LIMBO 방문자 안내 약도 (관제 화면 '약도 편집'에서 저장). 좌표는 지도와 같은 m\n"
        body += yaml.safe_dump(guide, allow_unicode=True, sort_keys=False, default_flow_style=None, width=200)
        atomic_write(self.path, body.encode("utf-8"))
        self._prune(guide["image"]["file"] if guide["image"] else None)
        return self.document()

    def save_image(self, data):
        """그림을 올린다. 이름은 내용의 해시라 같은 그림은 한 번만 저장된다. 약도를 저장해야 쓰인다"""
        if len(data) > MAX_IMAGE_BYTES:
            raise GuideError("image_too_large", f"Image must be at most {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        ext, width, height = image_info(data)
        name = f"image-{hashlib.sha256(data).hexdigest()[:16]}.{ext}"
        self.files.mkdir(parents=True, exist_ok=True)
        target = self.files / name
        if not target.exists():
            atomic_write(target, data)
        return dict(file=name, width=width, height=height, type=IMAGE_TYPES[ext])

    def image(self, name):
        """(바이트, 형식) 또는 None. 이름 규칙에 맞는 파일만"""
        if not IMAGE_NAME.fullmatch(name):
            return None
        try:
            return (self.files / name).read_bytes(), IMAGE_TYPES[name.rsplit(".", 1)[1]]
        except FileNotFoundError:
            return None

    def _prune(self, keep):
        """저장된 약도가 쓰지 않는 그림을 지운다. 올린 지 1시간이 안 된 것은 남긴다(다른 화면이 저장하기 전일 수 있음)"""
        import time
        if not self.files.is_dir():
            return
        for item in self.files.iterdir():
            if IMAGE_NAME.fullmatch(item.name) and item.name != keep and time.time() - item.stat().st_mtime > 3600:
                item.unlink(missing_ok=True)

    def public(self):
        """방문자 화면에 보일 약도: {revision, bounds, categories, areas, markers, image}. 보일 것이 없으면 None.
        파일이 없거나·깨졌거나·다른 지도로 그렸거나(위치가 어긋남)·비어 있으면 None. 기준점·지도 이름은 내보내지 않는다"""
        try:
            stat = self.path.stat()
            key = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            return None
        if self._public[0] == key:
            return self._public[1]
        try:
            guide, revision, _ = self.read()
        except (OSError, GuideError):
            guide = None
        view = None
        if guide is not None and guide["map"] in (None, self.map_name) and (guide["areas"] or guide["markers"] or guide["image"]):
            image = guide["image"]
            view = dict(revision=revision, bounds=guide["bounds"], categories=guide["categories"], areas=guide["areas"],
                        markers=guide["markers"],
                        image=None if image is None else dict(file=image["file"], width=image["width"], height=image["height"],
                                                              transform=image["transform"], show_areas=image["show_areas"]))
        self._public = (key, view)
        return view

    def raw(self):
        """내려받기용 파일 내용. 파일이 없으면 None"""
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None
