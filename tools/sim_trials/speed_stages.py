"""속도 명령이 어느 단계에서 깎이는지 본다. 사용법: speed_stages.py <bag 폴더>

/cmd_vel_nav(컨트롤러) → /cmd_vel_smoothed(속도 평활기) → /cmd_vel(collision monitor) 와
정답 위치로 잰 실제 속도를, 거의 직진하는 순간(회전 명령이 작을 때)만 골라 비교한다.
"""
import bisect
import math
import statistics as st
import sys

from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import rosbag2_py

STRAIGHT_WZ = 0.15   # rad/s, 이보다 회전 명령이 작으면 직진으로 본다
MOVING = 0.05        # m/s, 출발 전·정지 상태는 뺀다


def read(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    data = {}
    while reader.has_next():
        topic, raw, t = reader.read_next()
        data.setdefault(topic, []).append((t * 1e-9, deserialize_message(raw, types[topic])))
    return data


def twist(m):
    return m.twist if hasattr(m, 'twist') else m


def at(series, t):
    times = [s[0] for s in series]
    i = max(bisect.bisect_right(times, t) - 1, 0)
    return series[i][1]


def main():
    d = read(sys.argv[1])
    nav, smooth, final = d['/cmd_vel_nav'], d['/cmd_vel_smoothed'], d['/cmd_vel']
    gt = [(t, m.pose.pose.position.x, m.pose.pose.position.y) for t, m in d['/ground_truth/odom']]
    real = [(t1, math.hypot(x1 - x0, y1 - y0) / (t1 - t0)) for (t0, x0, y0), (t1, x1, y1) in zip(gt, gt[1:]) if t1 > t0]
    rows = []
    for t, m in nav:
        v, w = twist(m).linear.x, twist(m).angular.z
        if abs(w) > STRAIGHT_WZ or v < MOVING:
            continue
        rows.append((v, twist(at(smooth, t)).linear.x, twist(at(final, t)).linear.x, at([(a, (b,)) for a, b in real], t)[0]))
    if not rows:
        print('직진 구간 없음'); return
    print(f'직진하며 움직이는 순간 {len(rows)}개 (회전 < {STRAIGHT_WZ} rad/s)')
    for name, k in (('컨트롤러 출력 /cmd_vel_nav', 0), ('속도 평활 후 /cmd_vel_smoothed', 1), ('최종 /cmd_vel (collision monitor 후)', 2), ('실제 속도 (정답 위치)', 3)):
        v = sorted(r[k] for r in rows)
        print(f'  {name:36s} 평균 {st.mean(v):.2f}  중앙값 {v[len(v)//2]:.2f}  상위 10% {v[int(len(v)*0.9)]:.2f}  최대 {v[-1]:.2f} m/s')
    cut = sum(1 for r in rows if r[2] < r[0] - 0.05)
    print(f'  최종 속도가 컨트롤러 출력보다 0.05 m/s 넘게 낮은 순간: {cut}/{len(rows)} ({cut * 100 // len(rows)}%)')
    cm = d.get('/collision_monitor_state', [])
    print(f'  collision monitor 상태 메시지 {len(cm)}개, 종류: {sorted({m.action_type for _, m in cm})} (0 없음, 1 정지, 2 감속, 3 접근 감속, 4 제한)')


if __name__ == '__main__':
    main()
