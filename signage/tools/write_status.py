#!/usr/bin/env python3
"""bin_status.json / eco_metrics.json을 계약 형식대로 원자적으로 쓰는 도구.

수동 측정값 입력, 연동 시험, 데이터 생산자 구현 예시로 쓴다. 관측 시각(observed_at)은 지금.

  # 일반 60%, 재활용 측정 안 됨
  python tools/write_status.py bin --general 60 --recycling none --method manual_measured
  # 검증된 18/20건 (최근 24시간)
  python tools/write_status.py eco --correct 18 --total 20 --method human_audit
  # 둘 다 '값 없음' 초기 상태로
  python tools/write_status.py reset
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.bin_resolver import MEASUREMENT_METHODS  # noqa: E402
from app.eco_state_resolver import EVALUATION_METHODS  # noqa: E402
from app.util import atomic_write_json  # noqa: E402

TZ = ZoneInfo("Asia/Seoul")
EMPTY_BIN = {"fill_percent": None, "measurement_method": "unknown", "quality": "unavailable"}


def percent(text: str):
    if text.lower() in ("none", "null", "-"):
        return None
    value = float(text)
    if not 0 <= value <= 100:
        raise argparse.ArgumentTypeError("0~100 사이여야 합니다")
    return int(value) if value.is_integer() else value


def bin_payload(general, recycling, method: str, source: str) -> dict:
    def entry(v):
        return dict(EMPTY_BIN) if v is None else {"fill_percent": v, "measurement_method": method, "quality": "ok"}

    return {"schema_version": 1, "observed_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "source": source, "bins": {"general": entry(general), "recycling": entry(recycling)}}


def eco_payload(correct: int, total: int, method: str, window_hours: float, source: str) -> dict:
    now = datetime.now(TZ)
    return {"schema_version": 1, "observed_at": now.isoformat(timespec="seconds"),
            "window_start": (now - timedelta(hours=window_hours)).isoformat(timespec="seconds"),
            "window_end": now.isoformat(timespec="seconds"), "source": source, "evaluation_method": method,
            "verified_correct_count": correct, "verified_total_count": total, "quality": "ok"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bin", help="적재율 쓰기")
    b.add_argument("--general", type=percent, required=True, help="0~100 또는 none")
    b.add_argument("--recycling", type=percent, required=True, help="0~100 또는 none")
    b.add_argument("--method", choices=MEASUREMENT_METHODS, required=True)
    b.add_argument("--source", default="manual")
    b.add_argument("--file", default=str(ROOT / "data/bin_status.json"))
    e = sub.add_parser("eco", help="검증된 분리수거 건수 쓰기")
    e.add_argument("--correct", type=int, required=True)
    e.add_argument("--total", type=int, required=True)
    e.add_argument("--method", choices=EVALUATION_METHODS, required=True)
    e.add_argument("--window-hours", type=float, default=24)
    e.add_argument("--source", default="manual")
    e.add_argument("--file", default=str(ROOT / "data/eco_metrics.json"))
    sub.add_parser("reset", help="두 파일을 '값 없음' 초기 상태로")
    args = ap.parse_args()

    if args.cmd == "bin":
        atomic_write_json(args.file, bin_payload(args.general, args.recycling, args.method, args.source))
        print(f"썼음: {args.file}")
    elif args.cmd == "eco":
        if not 0 <= args.correct <= args.total:
            ap.error("0 <= correct <= total 이어야 합니다")
        atomic_write_json(args.file, eco_payload(args.correct, args.total, args.method, args.window_hours,
                                                 args.source))
        print(f"썼음: {args.file}")
    else:
        atomic_write_json(ROOT / "data/bin_status.json",
                          {"schema_version": 1, "observed_at": None, "source": "unavailable",
                           "bins": {"general": dict(EMPTY_BIN), "recycling": dict(EMPTY_BIN)}})
        atomic_write_json(ROOT / "data/eco_metrics.json",
                          {"schema_version": 1, "observed_at": None, "window_start": None, "window_end": None,
                           "source": "unavailable", "evaluation_method": "unknown",
                           "verified_correct_count": None, "verified_total_count": None,
                           "quality": "unavailable"})
        print("초기화했음: data/bin_status.json, data/eco_metrics.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
