"""레이싱 트랙(race_track) 한 바퀴를 Nav2로 돌고 시뮬레이션 시간을 잰다 (lab).
사용법: WORLD=race_track MAP=race_track_map ./sim_ctl.sh start 로 띄운 뒤 python3 race_lap.py
- 트랙 조절점(gen_track.py의 CONTROL)을 출발 직선 다음부터 차례로 지나 출발선 3 m 뒤에서 끝낸다
- 한 바퀴를 경로 하나로 주면 끝부분이 출발점 근처를 지나서 MPPI가 그쪽을 따라가 바로 "도착"으로 끝난다. 그래서 3구간으로 나눈다
"""
import math, time, re, rclpy
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateThroughPoses
from geometry_msgs.msg import PoseStamped
from rosgraph_msgs.msg import Clock
src = open(__import__('os').path.expanduser('~/limbo/limbo/src/') + 'limbo_simulation/tools/race_track/gen_track.py').read()
ctrl = eval(src[src.index('CONTROL = [') + len('CONTROL = '):src.index(']\n', src.index('CONTROL = [')) + 1])
pts = ctrl[4:] + [(-2.0, 0.0), (0.0, 0.0), (3.0, 0.0)]   # 한 바퀴 돌아 출발선 3 m 뒤에서 끝 (끝점이 출발점과 같으면 Nav2가 바로 도착으로 봄)
rclpy.init(); n = rclpy.create_node('lap'); sim = {'t': 0.0}
n.create_subscription(Clock, '/clock', lambda m: sim.__setitem__('t', m.clock.sec + m.clock.nanosec * 1e-9), 10)
def make_poses(seq):
    out = []
    for i, (x, y) in enumerate(seq):
        nx, ny = seq[i + 1] if i + 1 < len(seq) else (x + (x - seq[i - 1][0]), y + (y - seq[i - 1][1]))
        yaw = math.atan2(ny - y, nx - x)
        p = PoseStamped(); p.header.frame_id = 'map'; p.pose.position.x, p.pose.position.y = x, y
        p.pose.orientation.z, p.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2); out.append(p)
    return out
# 경로가 자기 출발점 근처를 다시 지나면 MPPI가 가까운 끝부분을 따라가 버려서 한 바퀴를 3구간으로 나눈다
third = len(pts) // 3
legs = [pts[:third], pts[third:2 * third], pts[2 * third:]]
ac = ActionClient(n, NavigateThroughPoses, '/navigate_through_poses'); ac.wait_for_server()
for _ in range(20): rclpy.spin_once(n, timeout_sec=0.1)
t0w, t0 = time.time(), sim['t']; ok = True
for k, leg in enumerate(legs):
    g = NavigateThroughPoses.Goal(); g.poses = make_poses(leg)
    f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f); r = f.result().get_result_async()
    while not r.done() and time.time() - t0w < 900: rclpy.spin_once(n, timeout_sec=0.1)
    st = r.done() and r.result().status == 4
    print(f'{k + 1}구간 {"성공" if st else "실패"}: 누적 시뮬레이션 {sim["t"] - t0:.1f}초', flush=True)
    ok = ok and st
length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
print(f'한 바퀴 {"성공" if ok else "실패"}: 시뮬레이션 {sim["t"] - t0:.1f}초 (조절점 사이 직선 거리 합 {length:.1f} m)', flush=True)
