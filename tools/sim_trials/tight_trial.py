"""좁은 곳 통과 시험 (가구 월드 aischool_2f_furnished, lab). 사용법: tight_trial.py <라벨> [반복 수, 기본 3]

한 바퀴 = 208 아래쪽 문(0.9 m)으로 들어가기 → 왼쪽 책상 통로(1.3 m) 끝까지 → 돌아서 내려오기 → 문으로 나가기.
구간마다 성공 여부와 걸린 시간(시뮬레이션 시간)을 logs/tight_results.csv에 한 줄씩 남긴다.
시뮬레이션은 sim_ctl.sh로 미리 띄워 둔다 (WORLD=aischool_2f_furnished MAP=aischool_2f_furnished_map).
"""
import math
import os
import sys
import time

import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rosgraph_msgs.msg import Clock

LEG_LIMIT = 150.0   # 구간 하나 최대 실제 시간 (s). 시뮬레이션이 실시간보다 느려서 넉넉히
# (구간 이름, x, y, 방향 °, 측정할지)
LEGS = [
    ('복도', -6.84, -0.24, 90, False),        # 문 밖 복도 (출발 위치 맞추기)
    ('문 들어가기', -8.75, 0.75, 180, True),   # 복도에서 90° 꺾어 0.9 m 문 통과
    ('통로 아래', -12.64, 0.75, 180, False),
    ('통로 끝', -12.64, 6.80, 90, True),       # 책상 통로 1.3 m를 끝까지 (교탁 때문에 막다른 곳)
    ('돌아 나오기', -12.64, 1.10, -90, True),  # 통로 끝에서 180° 돌아 내려오기
    ('문 나가기', -6.84, -0.24, -90, True),
]
LOG = os.path.expanduser('~/limbo_bags/sim_trials/logs/tight_results.csv')


def main():
    label = sys.argv[1]
    loops = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    rclpy.init()
    node = rclpy.create_node('tight_trial')
    sim = {'t': 0.0}
    node.create_subscription(Clock, '/clock', lambda m: sim.__setitem__('t', m.clock.sec + m.clock.nanosec * 1e-9), 10)
    client = ActionClient(node, NavigateToPose, '/navigate_to_pose')
    client.wait_for_server()
    new = not os.path.exists(LOG)
    out = open(LOG, 'a')
    if new:
        out.write('label,loop,leg,result,sim_sec\n')
    for loop in range(1, loops + 1):
        for name, x, y, yaw, measured in LEGS:
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = 'map'
            goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
            goal.pose.pose.orientation.z = math.sin(math.radians(yaw) / 2)
            goal.pose.pose.orientation.w = math.cos(math.radians(yaw) / 2)
            start_wall, start_sim = time.time(), sim['t']
            future = client.send_goal_async(goal)
            rclpy.spin_until_future_complete(node, future)
            handle = future.result()
            result = handle.get_result_async()
            while not result.done() and time.time() - start_wall < LEG_LIMIT:
                rclpy.spin_once(node, timeout_sec=0.1)
            if result.done():
                status = {4: 'OK', 5: 'CANCELED', 6: 'FAIL'}.get(result.result().status, 'FAIL')
            else:
                handle.cancel_goal_async()
                time.sleep(1.0)
                status = 'TIMEOUT'
            took = sim['t'] - start_sim
            print(f'{label} {loop}회 {name:8s} {status:8s} {took:6.1f}s', flush=True)
            if measured:
                out.write(f'{label},{loop},{name},{status},{took:.1f}\n')
                out.flush()


if __name__ == '__main__':
    main()
