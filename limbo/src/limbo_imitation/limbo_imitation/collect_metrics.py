"""
여러 바퀴 폴더의 metrics.csv를 표 한 장(CSV, stdout)으로 합친다. rclpy를 쓰지 않는다.

사용: ros2 run limbo_imitation collect_metrics ~/limbo_bags/imitation/* > all.csv
첫 열 run은 폴더 이름이다. metrics.csv가 없는 폴더(기록 중·비정상 종료)는 건너뛰고 stderr에 알린다.
"""

import csv
import os
import sys

from limbo_imitation import run_files


def collect_rows(folders):
    rows, skipped = [], []
    for folder in folders:
        found = run_files.read_metrics_csv(folder)
        if not found:
            skipped.append(folder)
        for row in found:
            rows.append({'run': os.path.basename(os.path.normpath(folder)), **row})
    return rows, skipped


def columns_of(rows):
    """열 순서는 처음 나온 순서. 지표 열이 늘어난 뒤의 바퀴가 섞여도 열이 빠지지 않게 합친다."""
    columns = []
    for row in rows:
        columns.extend(key for key in row if key not in columns)
    return columns


def main(argv=None):
    folders = sys.argv[1:] if argv is None else argv
    rows, skipped = collect_rows(folders)
    for folder in skipped:
        print(f'no {run_files.METRICS_FILE}: {folder}', file=sys.stderr)
    writer = csv.DictWriter(sys.stdout, fieldnames=columns_of(rows), restval='')
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
