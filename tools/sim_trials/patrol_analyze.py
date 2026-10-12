"""순찰 rosbag에서 '주행 중인데 로봇이 멈춰 있던 구간'을 찾아 원인 단서를 보여 준다.

사용법: patrol_analyze.py <patrol_*_bag 폴더>
멈춘 구간마다 세 단계 속도 명령의 평균을 비교한다.
- /cmd_vel_nav(MPPI)는 0이 아닌데 /cmd_vel(최종)이 0 → collision monitor가 막음
- /cmd_vel_nav부터 0 → MPPI가 스스로 멈춤 (목표 근처 cost, 경로 문제 등)
- /cmd_vel이 0이 아닌데 정답 위치가 안 움직임 → 실제로 막힘(충돌·헛돎)
속도와 멈춘 시간은 시뮬레이션 시간(정답 위치 메시지의 stamp)으로 잰다. 녹화 시각으로 재면
Gazebo가 잠깐 멈춘 것(예: 시험 중 Gazebo 화면을 붙일 때)까지 로봇이 멈춘 것으로 나온다.
그런 구간은 'Gazebo가 멈춘 구간'으로 따로 보여 준다.
"""
import bisect
import math
import sys

from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import rosbag2_py

STOP_SPEED = 0.03     # m/s, 정답 위치 기준 이보다 느리면 멈춤
MIN_STOP_SEC = 3.0    # 이 이상 멈춰 있던 구간만 본다 (시뮬레이션 시간)
SIM_PAUSE_SEC = 0.5   # 녹화 시각은 이만큼 흘렀는데 시뮬레이션 시간이 거의 안 흘렀으면 Gazebo가 멈춘 것
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
    # (녹화 시각, 시뮬레이션 시각, x, y). 다른 토픽과 맞출 때는 녹화 시각, 속도·시간은 시뮬레이션 시각을 쓴다
    gt = [(t, m.header.stamp.sec + m.header.stamp.nanosec * 1e-9, m.pose.pose.position.x, m.pose.pose.position.y)
          for t, m in data.get('/ground_truth/odom', [])]
    status = data.get('/navigate_through_poses/_action/status', [])
    if not status:
        # 도구 수정(2026-10-12 14:20) 전에 녹화한 bag. 전체를 주행 중으로 보고 근사로 분석한다
        print('주의: Nav2 상태 토픽이 없는 녹화라 전체 시간을 주행 중으로 보고 분석함. '
              'waypoint 대기(예: D 지점 5초)도 멈춤으로 나오니 위치로 구분할 것')
    active_times = [t for t, m in status]
    active_vals = [any(s.status == 2 for s in m.status_list) for t, m in status]

    def nav_active(t):
        if not status:
            return True
        i = bisect.bisect_right(active_times, t) - 1
        return i >= 0 and active_vals[i]

    pauses = [(t0, t1, s1 - s0) for (t0, s0, _, _), (t1, s1, _, _) in zip(gt, gt[1:])
              if t1 - t0 > SIM_PAUSE_SEC and s1 - s0 < 0.2 * (t1 - t0)]
    if pauses:
        print(f'Gazebo가 멈춘 구간 {len(pauses)}개 (녹화 시각은 흘렀는데 시뮬레이션 시간이 거의 안 흐름. 로봇 문제 아님)')
        for t0, t1, sim in pauses:
            print(f'  녹화 {t0 - gt[0][0]:6.1f}~{t1 - gt[0][0]:6.1f}초 ({t1 - t0:4.1f}초간, 시뮬레이션은 {sim:.2f}초)')

    stops, start = [], None
    for (t0, s0, x0, y0), (t1, s1, x1, y1) in zip(gt, gt[1:]):
        slow = math.hypot(x1 - x0, y1 - y0) / max(s1 - s0, 1e-6) < STOP_SPEED and nav_active(t1)
        if slow and start is None:
            start = (t0, s0, x0, y0)
        elif not slow and start is not None:
            if s0 - start[1] >= MIN_STOP_SEC:
                stops.append((start[0], t0, s0 - start[1], start[2], start[3]))
            start = None
    print(f'주행 중 {MIN_STOP_SEC:.0f}초 넘게 멈춘 구간 {len(stops)}개 (정답 위치, 시뮬레이션 시간 기준)')
    amcl = data.get('/amcl_pose', [])
    for s, e, sim_sec, x, y in stops:
        nav = mean_in(data.get('/cmd_vel_nav', []), s, e, lambda m: abs(twist(m).linear.x))
        smooth = mean_in(data.get('/cmd_vel_smoothed', []), s, e, lambda m: abs(twist(m).linear.x))
        final = mean_in(data.get('/cmd_vel', []), s, e, lambda m: abs(twist(m).linear.x))
        turn = mean_in(data.get('/cmd_vel', []), s, e, lambda m: abs(twist(m).angular.z))
        # 이 토픽은 상태가 바뀔 때만 나오므로 구간 시작 직전 마지막 상태도 포함한다 (서브 PC Q4)
        cm_all = data.get('/collision_monitor_state', [])
        cm_times = [t for t, _ in cm_all]
        before = bisect.bisect_right(cm_times, s) - 1
        cm = ([cm_all[before][1].action_type] if before >= 0 else []) + [m.action_type for t, m in cm_all if s < t <= e]
        cm_text = ', '.join(sorted({ACTIONS.get(a, str(a)) for a in cm})) or '상태 메시지 없음 (개입 없음으로 봄)'
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
        t0 = gt[0][0]
        print(f'  녹화 {s - t0:6.1f}~{e - t0:6.1f}초 (시뮬레이션 {sim_sec:4.1f}초간) 위치 ({x:6.2f},{y:5.2f})  속도 명령 MPPI {nav:.2f} → 평활 {smooth:.2f} → 최종 {final:.2f} m/s, '
              f'회전 {turn:.2f} rad/s  collision monitor: {cm_text}  위치 추정 오차 {err:.2f} m  → {hint}')


if __name__ == '__main__':
    main()
