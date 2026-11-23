#!/usr/bin/env python3
"""키오스크 브라우저가 Jetson에 주는 부하를 잰다 (표준 라이브러리만). PRD v0.3 열린 질문
「Jetson 브라우저가 로봇 다른 작업과 함께 /display를 8시간 돌릴 성능이 되는가」.

    python3 measure_load.py                      # display-kiosk 서비스의 브라우저를 5분 잰다
    python3 measure_load.py --seconds 600 --csv kiosk.csv
    python3 measure_load.py --no-browser         # 비교용: 브라우저를 끈 채(systemctl --user stop display-kiosk) 시스템만

잰 것 (interval초마다):
- 브라우저 CPU: 키오스크 프로세스와 그 자식 전체(렌더러·GPU 프로세스 포함). 100 % = 코어 하나
- 브라우저 메모리: PSS 합 (공유 메모리를 나눠 센 값이라 RSS 합보다 정확)
- 시스템 CPU(전체 코어 대비 %), load average(1분), 남은 메모리(MemAvailable)
같은 조건(Nav2 등 로봇 스택이 돌고 있을 때)에서 --no-browser와 한 번씩 재어 차이를 본다.
"""
import argparse
import csv
import os
import subprocess
import sys
import time

CLK = os.sysconf("SC_CLK_TCK")


def service_pid(name):
    try:
        out = subprocess.run(["systemctl", "--user", "show", "-p", "MainPID", "--value", name],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) if out and out != "0" else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def tree(root):
    """root와 그 자손 PID들 (/proc의 PPid로)"""
    children = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(int(entry))
    found, todo = [], [root]
    while todo:
        pid = todo.pop()
        found.append(pid)
        todo.extend(children.get(pid, []))
    return found


def cpu_ticks(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])   # utime + stime
    except (OSError, IndexError, ValueError):
        return None


def pss_kb(pid):
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


def system_ticks():
    with open("/proc/stat") as f:
        values = [int(v) for v in f.readline().split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def meminfo_mb(key):
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith(key + ":"):
                return int(line.split()[1]) / 1024
    return float("nan")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service", default="display-kiosk.service", help="잴 브라우저의 systemd 사용자 서비스")
    parser.add_argument("--pid", type=int, help="서비스 대신 이 PID와 그 자식을 잰다")
    parser.add_argument("--no-browser", action="store_true", help="브라우저 없이 시스템만 (비교 기준)")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--csv", help="구간별 값을 CSV로 저장")
    args = parser.parse_args()

    root = None
    if not args.no_browser:
        root = args.pid or service_pid(args.service)
        if root is None or not os.path.exists(f"/proc/{root}"):
            sys.exit(f"브라우저 프로세스를 찾지 못했습니다 ({args.service}). 서비스가 돌고 있는지, 또는 --pid / --no-browser")

    cores = os.cpu_count() or 1
    rows = []
    prev_proc = {}
    if root:
        for pid in tree(root):
            ticks = cpu_ticks(pid)
            if ticks is not None:
                prev_proc[pid] = ticks
    prev_total, prev_idle = system_ticks()
    prev_time = time.monotonic()
    end = prev_time + args.seconds
    print(f"{'초':>5} {'브라우저CPU%':>11} {'브라우저MB':>10} {'시스템CPU%':>10} {'load1':>6} {'남은MB':>8}")
    while time.monotonic() < end:
        time.sleep(args.interval)
        now = time.monotonic()
        dt = now - prev_time
        total, idle = system_ticks()
        system_cpu = 100 * (1 - (idle - prev_idle) / max(1, total - prev_total))
        browser_cpu = browser_mb = None
        if root:
            if not os.path.exists(f"/proc/{root}"):
                print("브라우저가 끝났습니다. 여기까지 정리합니다")
                break
            current = {}
            used = 0
            for pid in tree(root):
                ticks = cpu_ticks(pid)
                if ticks is None:
                    continue
                current[pid] = ticks
                used += ticks - prev_proc.get(pid, ticks)   # 새로 생긴 프로세스는 다음 구간부터
            prev_proc = current
            browser_cpu = 100 * used / CLK / dt
            browser_mb = sum(pss_kb(pid) for pid in current) / 1024
        load1 = os.getloadavg()[0]
        available = meminfo_mb("MemAvailable")
        row = dict(t=round(now - (end - args.seconds)), browser_cpu=browser_cpu, browser_mb=browser_mb,
                   system_cpu=system_cpu, load1=load1, available_mb=available)
        rows.append(row)
        fmt = lambda v, w: f"{'-':>{w}}" if v is None else f"{v:>{w}.1f}"
        print(f"{row['t']:>5} {fmt(browser_cpu, 11)} {fmt(browser_mb, 10)} {fmt(system_cpu, 10)} {load1:>6.2f} {available:>8.0f}")
        prev_total, prev_idle, prev_time = total, idle, now

    if not rows:
        sys.exit("잰 구간이 없습니다 (--seconds가 --interval보다 짧음)")
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f"\n정리 ({len(rows)}구간, 코어 {cores}개, 메모리 {meminfo_mb('MemTotal'):.0f} MB)")
    for key, label in (("browser_cpu", "브라우저 CPU % (코어 하나=100)"), ("browser_mb", "브라우저 메모리 MB (PSS)"),
                       ("system_cpu", "시스템 CPU % (전체 코어 대비)"), ("load1", "load average 1분"), ("available_mb", "남은 메모리 MB")):
        values = [r[key] for r in rows if r[key] is not None]
        if values:
            print(f"  {label:<32} 평균 {sum(values) / len(values):8.1f}  최대 {max(values):8.1f}  최소 {min(values):8.1f}")


if __name__ == "__main__":
    main()
