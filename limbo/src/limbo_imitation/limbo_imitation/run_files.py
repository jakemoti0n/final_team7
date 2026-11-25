"""
한 바퀴 기록 폴더의 이름·meta.json·metrics.csv를 다룬다. rclpy를 쓰지 않는다.

폴더 구조: <output_root>/<YYYYMMDD_HHMMSS>_<번호>_<모드>/
  bag/          ros2 bag record 결과
  meta.json     누가·어떤 모드·어떤 지도와 경유점으로 달렸는지
  metrics.csv   지표 한 줄(열 이름은 metrics.ROW_COLUMNS)

한 바퀴를 닫는 단계(finish_run)도 여기 둔다. 노드 없이 가짜 bag 프로세스로 시험하려는 것이다.
"""

import csv
import hashlib
import json
import os
import signal
import subprocess

from limbo_imitation import metrics

META_FILE = 'meta.json'
METRICS_FILE = 'metrics.csv'
BAG_DIR = 'bag'
HASH_CHUNK_BYTES = 1 << 20


def run_folder_name(start, number, mode):
    """start는 datetime. 같은 초에 두 바퀴가 시작돼도 번호로 갈린다."""
    return f"{start.strftime('%Y%m%d_%H%M%S')}_{number:02d}_{mode}"


def file_sha256(path):
    """파일 내용의 sha256. 경로가 비었거나 파일이 없으면 None.

    경로만 남기면 나중에 같은 이름의 파일이 고쳐졌을 때 어느 판으로 달렸는지 모른다.
    """
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_BYTES), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_meta(mode, driver, waypoints_file, map_yaml, model_file, note, start_iso):
    return {
        'mode': mode,
        'driver': driver,
        'waypoints_file': waypoints_file or None,
        'waypoints_sha256': file_sha256(waypoints_file),
        'map_yaml': map_yaml or None,
        'map_sha256': file_sha256(map_yaml),
        'model_file': model_file or None,
        'model_sha256': file_sha256(model_file),
        'start_time': start_iso,
        'end_time': None,
        'end_reason': None,
        'note': note,
    }


def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_metrics_csv(path, row, columns):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerow(row)


def read_metrics_csv(folder):
    """폴더의 metrics.csv 줄들(dict). 파일이 없으면 빈 목록(기록 중이거나 비정상 종료된 바퀴)."""
    path = os.path.join(folder, METRICS_FILE)
    if not os.path.isfile(path):
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def signal_bag(bag):
    """bag이 아직 돌면 SIGINT를 보낸다(기다리지 않음).

    터미널 Ctrl+C는 같은 프로세스 그룹의 bag에도 직접 가서 bag이 먼저 끝나 있을 수 있다.
    poll()이 그런 bag을 거둔다.
    """
    if bag.poll() is None:
        bag.send_signal(signal.SIGINT)


def wait_bag(bag, timeout):
    """bag이 끝나기를 timeout초까지 기다려 거둔다. 거뒀으면 True.

    안 끝나도 SIGTERM은 보내지 않는다. PM 승인 뒤에만 쓰기로 한 수단이다(TROUBLESHOOTING 2026-11-10).
    """
    try:
        bag.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def finish_run(folder, meta, log, settings, bag, bag_timeout):
    """한 바퀴를 닫는다: bag에 SIGINT → metrics.csv·meta.json 쓰기 → bag 거두기.

    meta의 end_time·end_reason과 log.end_time은 부르는 쪽이 채운다.
    결과 파일을 bag이 닫히기를 기다리기 전에 쓴다. bag 마무리가 늦거나 종료 중 두 번째 신호가
    와도 지표와 끝난 시각은 남게 하려는 것이다. (지표 한 줄, bag을 거뒀는지)를 낸다.
    """
    signal_bag(bag)
    row = metrics.metrics_row(metrics.compute_metrics(log, settings), settings)
    write_metrics_csv(os.path.join(folder, METRICS_FILE), row, metrics.ROW_COLUMNS)
    write_json(os.path.join(folder, META_FILE), meta)
    return row, wait_bag(bag, bag_timeout)
