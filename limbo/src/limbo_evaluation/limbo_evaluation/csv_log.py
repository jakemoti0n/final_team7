"""평가 결과를 CSV 파일에 한 줄씩 덧붙인다."""

import csv
import os


def append_row(path, row):
    """파일이 없으면 열 이름 줄을 먼저 쓴다."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if is_new:
            writer.writeheader()
        writer.writerow(row)
