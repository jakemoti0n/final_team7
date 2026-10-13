"""지도(SLAM pgm)와 순찰 waypoint를 화면용으로 읽는다. 서버 시작 때 한 번만 (docs/CONTROL_API_DRAFT.md §4)."""
from pathlib import Path
import struct
import zlib

import yaml


def read_pgm(path):
    """P5(binary) PGM → (가로, 세로, 바이트). 주석(#) 허용, 최대값 255 이하만."""
    data = Path(path).read_bytes()
    tokens, pos = [], 0
    while len(tokens) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        tokens.append(data[pos:end])
        pos = end
    magic, width, height, maxval = tokens[0], int(tokens[1]), int(tokens[2]), int(tokens[3])
    if magic != b"P5" or not 0 < maxval <= 255:
        raise ValueError("only 8-bit binary PGM (P5) is supported")
    pixels = data[pos + 1:pos + 1 + width * height]
    if len(pixels) != width * height:
        raise ValueError("truncated PGM")
    return width, height, pixels


def png_gray(width, height, pixels):
    """8비트 회색조 PNG (외부 라이브러리 없이)."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    rows = b"".join(b"\x00" + pixels[y * width:(y + 1) * width] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def load(map_yaml, waypoints_yaml=None, base=None):
    """(메타데이터, PNG 바이트). 경로가 상대경로면 base(저장소 루트) 기준."""
    def resolve(value):
        path = Path(value)
        return path if path.is_absolute() or base is None else Path(base) / path
    map_path = resolve(map_yaml)
    meta = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    image = Path(meta["image"])
    image = image if image.is_absolute() else map_path.parent / image
    width, height, pixels = read_pgm(image)
    waypoints = []
    if waypoints_yaml:
        for w in yaml.safe_load(resolve(waypoints_yaml).read_text(encoding="utf-8"))["waypoints"]:
            waypoints.append(dict(name=str(w["name"]), type=str(w["type"]),
                                  x=float(w["x"]), y=float(w["y"])))
    origin = [float(v) for v in meta["origin"]]
    return dict(resolution=float(meta["resolution"]), origin=origin, width=width, height=height,
                image="/api/v1/map.png", waypoints=waypoints), png_gray(width, height, pixels)
