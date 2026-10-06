"""Development-only synthetic telemetry. Never run against a live robot server."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import time
import urllib.error
import urllib.request
import uuid

KEYS = ("odom", "lidar_raw", "lidar_filtered", "camera_raw")


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def empty(session=None, sequence=1):
    return dict(schema_version=1, robot_id="LIMBO-01", bridge_session_id=session or str(uuid.uuid4()),
                sequence=sequence, sent_at=utc(), source_clock="ros_sim",
                topics={key: dict(header_stamp=None, last_received_at=None, age_ms=None,
                                 received_count=0, receive_hz=None) for key in KEYS},
                motion=dict(linear_speed_mps=None, angular_velocity_radps=None, last_received_at=None, age_ms=None))


def sample(session=None, sequence=1, speed=.25, angular=0.):
    result = empty(session, sequence)
    for topic in result["topics"].values():
        topic.update(header_stamp=dict(sec=0, nanosec=0), last_received_at=result["sent_at"],
                     age_ms=0., received_count=sequence, receive_hz=10.)
    result["motion"].update(linear_speed_mps=speed, angular_velocity_radps=angular,
                             last_received_at=result["sent_at"], age_ms=0.)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--robot-id", default="LIMBO-01")
    parser.add_argument("--scenario", choices=["normal", "empty", "partial", "all-stopped", "bridge-stopped",
                                              "new-session", "duplicate", "out-of-order", "invalid", "zero", "rotation", "invalid-motion"], default="normal")
    parser.add_argument("--duration", type=float, default=20)
    args = parser.parse_args()
    print("개발용 가상 송신기 · 실제 로봇 데이터가 아닙니다. 전용 서버에서만 사용하세요.", flush=True)
    started = time.monotonic()
    session = str(uuid.uuid4())
    frozen = sample(session)
    sequence = 0
    changed = False
    while time.monotonic() - started < args.duration:
        elapsed = time.monotonic() - started
        sequence += 1
        if args.scenario == "bridge-stopped" and sequence > 1:
            time.sleep(.1)
            continue
        if args.scenario == "new-session" and elapsed >= 5 and not changed:
            session, sequence, changed = str(uuid.uuid4()), 1, True
        payload = empty(session, sequence) if args.scenario == "empty" or changed else sample(session, sequence)
        payload["robot_id"] = args.robot_id
        for key in KEYS:
            if args.scenario == "all-stopped" or (args.scenario == "partial" and key == "lidar_filtered"):
                payload["topics"][key] = deepcopy(frozen["topics"][key])
                payload["topics"][key]["age_ms"] = elapsed * 1000
                payload["topics"][key]["receive_hz"] = 0.
        if args.scenario == "all-stopped":
            payload["motion"] = deepcopy(frozen["motion"])
            payload["motion"]["age_ms"] = elapsed * 1000
        if args.scenario in ("zero", "rotation"):
            payload["motion"].update(linear_speed_mps=0., angular_velocity_radps=.4 if args.scenario == "rotation" else 0.)
        if args.scenario == "invalid-motion":
            payload["motion"] = empty()["motion"]
        if args.scenario == "duplicate":
            payload["sequence"] = 1
        if args.scenario == "out-of-order":
            payload["sequence"] = 100 if sequence == 1 else 1
        if args.scenario == "invalid":
            payload["unexpected"] = True
        request = urllib.request.Request(args.url.rstrip("/") + "/api/v1/telemetry",
                                         data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=1) as response:
                print(response.status, response.read().decode(), flush=True)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(str(exc), flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
