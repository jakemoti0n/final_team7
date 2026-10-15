"""전역 경로 계획 계산 시간 재기. 주행하지 않고 compute_path_to_pose 액션을 같은 목표로 N번 불러 응답 시간을 잰다.

사용법: plan_time.py <라벨> [반복=10]
목표: 홀(0,0)에서 지도 안 먼 곳 4군데 (아래 GOALS). 출력: 목표별 평균/최대 ms, 경로 길이. 로그 CSV는 ~/limbo_bags/sim_trials/logs/plan_time_<라벨>.csv
"""
import csv, math, os, sys, time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from nav2_msgs.action import ComputePathToPose
from geometry_msgs.msg import PoseStamped

GOALS = [('왼쪽 복도 위쪽 끝', -6.8, 10.0), ('위쪽 복도 동쪽', 3.5, 9.8), ('홀 서쪽', -5.0, 0.5), ('왼쪽 복도 아래', -13.0, -1.1)]


def main():
    label = sys.argv[1]; reps = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    rclpy.init(); n = Node('plan_time'); ac = ActionClient(n, ComputePathToPose, '/compute_path_to_pose'); ac.wait_for_server()
    rows = []
    for name, x, y in GOALS:
        times, length = [], float('nan')
        for _ in range(reps):
            g = ComputePathToPose.Goal(); g.goal.header.frame_id = 'map'
            g.goal.pose.position.x, g.goal.pose.position.y, g.goal.pose.orientation.w = x, y, 1.0
            g.use_start = False; g.planner_id = 'GridBased'
            t0 = time.monotonic(); f = ac.send_goal_async(g); rclpy.spin_until_future_complete(n, f, timeout_sec=10.0)
            if not f.done() or not f.result().accepted:
                times.append(float('nan')); continue
            r = f.result().get_result_async(); rclpy.spin_until_future_complete(n, r, timeout_sec=20.0)
            times.append((time.monotonic() - t0) * 1000.0)
            if r.done():
                pts = r.result().result.path.poses
                length = sum(math.dist((a.pose.position.x, a.pose.position.y), (b.pose.position.x, b.pose.position.y)) for a, b in zip(pts, pts[1:]))
                # 액션 결과에 planning_time 필드가 있으면 그것도 (왕복 지연을 뺀 순수 계산 시간)
                pt = getattr(r.result().result, 'planning_time', None)
                if pt is not None:
                    times[-1] = (times[-1], pt.sec * 1000.0 + pt.nanosec / 1e6)
        rt = [t[0] if isinstance(t, tuple) else t for t in times]; pure = [t[1] for t in times if isinstance(t, tuple)]
        ok = [t for t in rt if t == t]
        row = {'label': label, 'goal': name, 'reps': reps, 'ok': len(ok), 'rtt_mean_ms': round(sum(ok) / len(ok), 1) if ok else '',
               'rtt_max_ms': round(max(ok), 1) if ok else '', 'plan_mean_ms': round(sum(pure) / len(pure), 2) if pure else '',
               'plan_max_ms': round(max(pure), 2) if pure else '', 'path_len_m': round(length, 2)}
        rows.append(row); print(row, flush=True)
    out = os.path.expanduser(f'~/limbo_bags/sim_trials/logs/plan_time_{label}.csv')
    with open(out, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('CSV', out); n.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    main()
