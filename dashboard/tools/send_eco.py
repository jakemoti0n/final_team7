"""분리수거 성공률을 서버에 한 번 보낸다 (Raspberry Pi 프로그램이 생기기 전 시험용, 표준 라이브러리만).

Pi가 보낼 것과 같은 묶음(POST /api/v1/eco)을 만들어 보내고, 서버가 판정한 결과를 찍는다.
계약: signage/docs/PRD_로봇_하단_디스플레이_v0.3.md 「분리수거 성공률 계약」, 서버 검사: dashboard/server/eco.py

  # 로컬 개발 서버 (config.json의 allow_no_robot_token이면 토큰 없이)
  python3 dashboard/tools/send_eco.py --correct 18 --total 20             # → positive (90 %)
  python3 dashboard/tools/send_eco.py --correct 13 --total 20             # → negative (65 %)
  python3 dashboard/tools/send_eco.py --correct 5 --total 5               # → initial (20건 미만)
  # 클라우드 (ECO_TOKEN은 서버 .env와 같은 값)
  ECO_TOKEN=... python3 dashboard/tools/send_eco.py --url https://<도메인> --correct 18 --total 20

서버는 마지막으로 받은 뒤 600초가 지나면 초기 나무로 돌아간다. 계속 보이게 하려면 --every 60으로 1분마다 보낸다.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
import urllib.error
import urllib.request


def body(args):
    now = datetime.now(timezone.utc).astimezone()
    return {
        "schema_version": 1,
        "observed_at": now.isoformat(timespec="seconds"),
        "window_start": (now - timedelta(hours=args.hours)).isoformat(timespec="seconds"),   # 수거함을 비운 시각
        "window_end": now.isoformat(timespec="seconds"),
        "source": args.source,
        "evaluation_method": args.method,
        "verified_correct_count": args.correct,
        "verified_total_count": args.total,
        "quality": args.quality,
    }


def send(args):
    request = urllib.request.Request(args.url.rstrip("/") + "/api/v1/eco", data=json.dumps(body(args)).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    token = os.environ.get("ECO_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(json.loads(response.read())["eco"])
            return True
    except urllib.error.HTTPError as exc:
        print(f"{exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
    except OSError as exc:
        print(f"cannot reach {args.url}: {exc}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="Send one recycling result to the dashboard (test sender)")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="dashboard server (default: local)")
    parser.add_argument("--correct", type=int, required=True, help="items found in the right bin")
    parser.add_argument("--total", type=int, required=True, help="items checked since the bin was emptied")
    parser.add_argument("--hours", type=float, default=1, help="hours since the bin was emptied (window_start)")
    parser.add_argument("--method", default="ai_bin_inspection", help="evaluation_method (default: ai_bin_inspection)")
    parser.add_argument("--quality", default="ok")
    parser.add_argument("--source", default="send_eco.py")
    parser.add_argument("--every", type=float, help="keep sending every N seconds (Ctrl+C to stop)")
    args = parser.parse_args()
    if args.every is None:
        sys.exit(0 if send(args) else 1)
    while True:
        send(args)
        time.sleep(args.every)


if __name__ == "__main__":
    main()
