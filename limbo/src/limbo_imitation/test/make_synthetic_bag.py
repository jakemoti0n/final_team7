"""
가짜 바퀴 기록 폴더 하나(bag·meta.json·metrics.csv·경유점 yaml)를 만든다. e2e_synthetic.sh가 쓴다.

실물 bag이 없는 PC에서 build_dataset → train_policy → policy_node 흐름을 한 번 돌려 보기 위한 것이라
운전은 일부러 단순하다: 사각 방 안에서 직진하다가 좌회전(seed마다 속도·회전에 작은 잡음).
기록기(run_recorder)와 같은 토픽 이름·형식으로 쓴다. 메시지 시각 = bag 시각(ros2 bag play --clock과 맞게).
사용: python3 make_synthetic_bag.py <출력 루트> --seed 1
"""

import argparse
from datetime import datetime
import json
import math
import os

from geometry_msgs.msg import TransformStamped, Twist
from limbo_imitation import metrics, run_files
from limbo_interfaces.msg import PatrolState, PersonPrediction, PersonPredictionArray
from nav_msgs.msg import Odometry
from rclpy.serialization import serialize_message
import rosbag2_py
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

START_SEC = 1_764_000_000.0  # 아무 날짜. --clock 재생의 sim time이 된다
DURATION = 30.0
TURN_AT = 15.0
DT = 0.05            # 20 Hz: odom·tf·teleop
SCAN_EVERY = 2       # 10 Hz
SCAN_RAYS = 360
ROOM = (-2.0, -4.0, 14.0, 10.0)  # x_min, y_min, x_max, y_max 지도 좌표 벽
MAP_TO_ODOM = (1.0, 0.5, 0.1)
WAYPOINTS = [(8.0, 0.5, 'pass'), (6.0, 6.0, 'stop')]
TOPICS = {
    '/scan': 'sensor_msgs/msg/LaserScan', '/odom': 'nav_msgs/msg/Odometry',
    '/tf': 'tf2_msgs/msg/TFMessage', '/patrol/state': 'limbo_interfaces/msg/PatrolState',
    '/person_detector/predictions': 'limbo_interfaces/msg/PersonPredictionArray',
    '/drive_mode': 'std_msgs/msg/String', '/cmd_vel_teleop': 'geometry_msgs/msg/Twist',
    '/cmd_vel_arbiter': 'geometry_msgs/msg/Twist', '/cmd_vel': 'geometry_msgs/msg/Twist',
}


def stamp_of(t):
    sec = int(t)
    return sec, int(round((t - sec) * 1e9))


def ray_to_room(x, y, angle):
    """방 안의 점에서 angle 방향으로 벽까지 거리."""
    x_min, y_min, x_max, y_max = ROOM
    dx, dy = math.cos(angle), math.sin(angle)
    hits = []
    if abs(dx) > 1e-9:
        hits.append(((x_max if dx > 0 else x_min) - x) / dx)
    if abs(dy) > 1e-9:
        hits.append(((y_max if dy > 0 else y_min) - y) / dy)
    return min(h for h in hits if h > 0)


def command_at(t, rng_v, rng_w):
    if t < TURN_AT:
        return 0.4 + rng_v, 0.0 + rng_w
    return 0.3 + rng_v, 0.5 + rng_w


def scan_msg(t, pose_map):
    x, y, yaw = pose_map
    msg = LaserScan()
    msg.header.stamp.sec, msg.header.stamp.nanosec = stamp_of(t)
    msg.header.frame_id = 'base_footprint'
    msg.angle_min, msg.angle_increment = -math.pi, 2 * math.pi / SCAN_RAYS
    msg.angle_max = msg.angle_min + msg.angle_increment * (SCAN_RAYS - 1)
    msg.range_min, msg.range_max = 0.1, 20.0
    msg.ranges = [ray_to_room(x, y, yaw + msg.angle_min + i * msg.angle_increment)
                  for i in range(SCAN_RAYS)]
    return msg


def odom_msg(t, pose, v, w):
    msg = Odometry()
    msg.header.stamp.sec, msg.header.stamp.nanosec = stamp_of(t)
    msg.header.frame_id, msg.child_frame_id = 'odom', 'base_footprint'
    msg.pose.pose.position.x, msg.pose.pose.position.y = pose[0], pose[1]
    msg.pose.pose.orientation.z, msg.pose.pose.orientation.w = (math.sin(pose[2] / 2),
                                                                math.cos(pose[2] / 2))
    msg.twist.twist.linear.x, msg.twist.twist.angular.z = v, w
    return msg


def transform(t, parent, child, pose):
    tf = TransformStamped()
    tf.header.stamp.sec, tf.header.stamp.nanosec = stamp_of(t)
    tf.header.frame_id, tf.child_frame_id = parent, child
    tf.transform.translation.x, tf.transform.translation.y = pose[0], pose[1]
    tf.transform.rotation.z, tf.transform.rotation.w = math.sin(pose[2] / 2), math.cos(pose[2] / 2)
    return tf


def twist(v, w):
    msg = Twist()
    msg.linear.x, msg.angular.z = v, w
    return msg


def patrol_msg(t, index):
    msg = PatrolState(state=PatrolState.PATROLLING, waypoint_index=index,
                      waypoint_count=len(WAYPOINTS), waypoint_name=f'P{index}')
    msg.stamp.sec, msg.stamp.nanosec = stamp_of(t)
    return msg


def people_msg(t):
    """방 안쪽에서 천천히 걷는 사람 한 명(odom 좌표). 사람 칸이 늘 비어 있지 않게."""
    msg = PersonPredictionArray()
    msg.header.stamp.sec, msg.header.stamp.nanosec = stamp_of(t)
    msg.header.frame_id = 'odom'
    person = PersonPrediction(person_id=1)
    person.current_position.x, person.current_position.y = 6.0, 3.0 + 0.1 * (t - START_SEC)
    person.velocity.y = 0.1
    msg.predictions = [person]
    return msg


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], a[2] + b[2])


def messages(seed):
    """(topic, 메시지, 시각) 순서대로."""
    import random
    rng = random.Random(seed)
    pose = (0.0, 0.0, 0.0)
    noise_v, noise_w = rng.uniform(-0.03, 0.03), rng.uniform(-0.05, 0.05)
    yield '/patrol/state', patrol_msg(START_SEC, 0), START_SEC
    for i in range(int(DURATION / DT)):
        t = START_SEC + i * DT
        v, w = command_at(i * DT, noise_v, noise_w)
        if i == int(round(TURN_AT / DT)):
            yield '/patrol/state', patrol_msg(t, 1), t
        if i % int(round(1.0 / DT)) == 0:
            payload = {'source': 'teleop', 'mode': 'manual', 'reason': 'deadman held', 'stamp': t}
            yield '/drive_mode', String(data=json.dumps(payload)), t
        for topic in ('/cmd_vel_teleop', '/cmd_vel_arbiter', '/cmd_vel'):
            yield topic, twist(v, w), t
        yield '/odom', odom_msg(t, pose, v, w), t
        yield '/tf', TFMessage(transforms=[transform(t, 'map', 'odom', MAP_TO_ODOM),
                                           transform(t, 'odom', 'base_footprint', pose)]), t
        if i % SCAN_EVERY == 0:
            yield '/scan', scan_msg(t, compose(MAP_TO_ODOM, pose)), t
            yield '/person_detector/predictions', people_msg(t), t
        pose = (pose[0] + v * math.cos(pose[2]) * DT, pose[1] + v * math.sin(pose[2]) * DT,
                pose[2] + w * DT)


def write_bag(bag_dir, seed):
    writer = rosbag2_py.SequentialWriter()
    writer.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id='mcap'),
                rosbag2_py.ConverterOptions('cdr', 'cdr'))
    for i, (name, kind) in enumerate(TOPICS.items()):
        writer.create_topic(rosbag2_py.TopicMetadata(i, name, kind, 'cdr'))
    for topic, msg, t in messages(seed):
        writer.write(topic, serialize_message(msg), int(round(t * 1e9)))
    del writer


def write_waypoints(path):
    lines = ['waypoints:']
    for i, (x, y, kind) in enumerate(WAYPOINTS):
        lines.append(f'  - {{name: P{i}, type: {kind}, x: {x}, y: {y}, yaw: 0.0, wait_sec: 0}}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--seed', type=int, default=1)
    args = parser.parse_args()
    os.makedirs(args.root, exist_ok=True)
    waypoints = os.path.join(args.root, 'synthetic_waypoints.yaml')
    write_waypoints(waypoints)
    folder = os.path.join(args.root, run_files.run_folder_name(datetime.now(), args.seed,
                                                               'manual'))
    os.makedirs(folder)
    write_bag(os.path.join(folder, run_files.BAG_DIR), args.seed)
    meta = run_files.build_meta('manual', 'synthetic', waypoints, '', '', f'seed {args.seed}',
                                datetime.now().isoformat(timespec='seconds'))
    run_files.write_json(os.path.join(folder, run_files.META_FILE), meta)
    log = metrics.RunLog(start_time=0.0, end_time=DURATION,
                         patrol_states=[(0.0, 'patrolling'), (DURATION, 'completed')])
    row = metrics.metrics_row(metrics.compute_metrics(log), metrics.DEFAULT_SETTINGS)
    run_files.write_metrics_csv(os.path.join(folder, run_files.METRICS_FILE), row,
                                metrics.ROW_COLUMNS)
    print(folder)


if __name__ == '__main__':
    main()
