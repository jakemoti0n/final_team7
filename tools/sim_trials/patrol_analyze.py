"""순찰 rosbag에서 '주행 중인데 로봇이 멈춰 있던 구간'을 찾아 원인 단서를 보여 준다.

사용법: patrol_analyze.py <patrol_*_bag 폴더>
멈춘 구간마다 세 단계 속도 명령의 평균을 비교한다.
- /cmd_vel_nav(MPPI)는 0이 아닌데 /cmd_vel(최종)이 0 → collision monitor가 막음
- /cmd_vel_nav부터 0 → MPPI가 스스로 멈춤 (목표 근처 cost, 경로 문제 등)
- /cmd_vel이 0이 아닌데 정답 위치가 안 움직임 → 실제로 막힘(충돌·헛돎)
"""
import bisect
import math
import sys

from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import rosbag2_py

STOP_SPEED = 0.03     # m/s, 정답 위치 기준 이보다 느리면 멈춤
MIN_STOP_SEC = 3.0    # 이 이상 멈춰 있던 구간만 본다
ACTIONS = {0: '개입 없음', 1: '정지(STOP)', 2: '감속(SLOWDOWN)', 3: '접근 감속(APPROACH)', 4: '제한(LIMIT)'}


def read(path):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id='mcap'), rosbag2_py.ConverterOptions('', ''))
    types = {t.name: get_message(t.type) for t in reader.get_all_topics_and_types()}
    data = {}
    while reader.has_next():
        topic, raw, t = reader.read_next()
        data.setdefault(topic, []).append((t * 1e-9, deserialize_message(raw, types[topic])))
    return data


def twist(msg):
    return msg.twist if hasattr(msg, 'twist') else msg


def mean_in(series, t0, t1, value):
    v = [value(m) for t, m in series if t0 <= t <= t1]
    return sum(v) / len(v) if v else float('nan')


def main():
    data = read(sys.argv[1])
    gt = [(t, m.pose.pose.position.x, m.pose.pose.position.y) for t, m in data.get('/ground_truth/odom', [])]
    status = data.get('/navigate_through_poses/_action/status', [])
    active_times = [t for t, m in status]
    active_vals = [any(s.status == 2 for s in m.status_list) for t, m in status]

    def nav_active(t):
        i = bisect.bisect_right(active_times, t) - 1
        return i >= 0 and active_vals[i]

    stops, start = [], None
    for (t0, x0, y0), (t1, x1, y1) in zip(gt, gt[1:]):
        slow = math.hypot(x1 - x0, y1 - y0) / max(t1 - t0, 1e-6) < STOP_SPEED and nav_active(t1)
        if slow and start is None:
            start = (t0, x0, y0)
        elif not slow and start is not None:
            if t0 - start[0] >= MIN_STOP_SEC:
                stops.append((start[0], t0, start[1], start[2]))
            start = None
    print(f'주행 중 {MIN_STOP_SEC:.0f}초 넘게 멈춘 구간 {len(stops)}개 (정답 위치 기준)')
    amcl = data.get('/amcl_pose', [])
    for s, e, x, y in stops:
        nav = mean_in(data.get('/cmd_vel_nav', []), s, e, lambda m: abs(twist(m).linear.x))
        smooth = mean_in(data.get('/cmd_vel_smoothed', []), s, e, lambda m: abs(twist(m).linear.x))
        final = mean_in(data.get('/cmd_vel', []), s, e, lambda m: abs(twist(m).linear.x))
        turn = mean_in(data.get('/cmd_vel', []), s, e, lambda m: abs(twist(m).angular.z))
        cm = [m.action_type for t, m in data.get('/collision_monitor_state', []) if s <= t <= e]
        cm_text = ', '.join(sorted({ACTIONS.get(a, str(a)) for a in cm})) or '기록 없음'
        near = [m for t, m in amcl if s <= t <= e]
        err = (math.hypot(near[-1].pose.pose.position.x - x, near[-1].pose.pose.position.y - y)
               if near else float('nan'))
        if final < 0.02 and nav >= 0.05:
            hint = 'collision monitor가 막음'
        elif nav < 0.02 and turn < 0.05:
            hint = 'MPPI가 스스로 멈춤'
        elif final >= 0.05:
            hint = '명령은 나가는데 안 움직임 (막힘·헛돎)'
        else:
            hint = '제자리 회전 또는 판단 어려움'
        print(f'  {s:7.1f}~{e:7.1f}s ({e - s:4.1f}초) 위치 ({x:6.2f},{y:5.2f})  속도 명령 MPPI {nav:.2f} → 평활 {smooth:.2f} → 최종 {final:.2f} m/s, '
              f'회전 {turn:.2f} rad/s  collision monitor: {cm_text}  위치 추정 오차 {err:.2f} m  → {hint}')


if __name__ == '__main__':
    main()
