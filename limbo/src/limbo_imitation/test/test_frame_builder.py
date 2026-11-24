"""입력 조립(frame_builder) 테스트. 기대값은 손으로 계산했다."""

import ast
import math
import os

from limbo_imitation import dataset, features, frame_builder
import numpy as np
import pytest

PACKAGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'limbo_imitation')


def test_compose_poses_turn_then_forward():
    # map→odom: (2, 0)에서 왼쪽 90°. odom→base: odom 앞 1 m → 지도에서는 위(+y)로 1 m
    x, y, yaw = frame_builder.compose_poses((2.0, 0.0, math.pi / 2), (1.0, 0.0, 0.0))
    assert (x, y, yaw) == (pytest.approx(2.0), pytest.approx(1.0), pytest.approx(math.pi / 2))


def test_compose_poses_wraps_yaw():
    _, _, yaw = frame_builder.compose_poses((0.0, 0.0, 3.0), (0.0, 0.0, 1.0))
    assert yaw == pytest.approx(4.0 - 2 * math.pi)


def test_yaw_from_quaternion_ninety_degrees():
    half = math.pi / 4
    assert frame_builder.yaw_from_quaternion(0.0, 0.0, math.sin(half),
                                             math.cos(half)) == pytest.approx(math.pi / 2)


def test_people_in_base_rotates_position_and_velocity():
    # 로봇 (1, 1)에서 +y를 봄. 사람 (1, 2)가 +y로 1 m/s → 로봇 앞 1 m, 로봇에서 멀어지는 방향(+x)
    result = frame_builder.people_in_base([(1.0, 2.0, 0.0, 1.0)], (1.0, 1.0, math.pi / 2))
    np.testing.assert_allclose(result[0], (1.0, 0.0, 1.0, 0.0), atol=1e-12)


def test_input_problem_order_and_waypoint():
    fresh = {'tf': 0.0, 'odom': 0.0, 'people': 0.1}
    assert frame_builder.input_problem(fresh, (0, 0, False), 0.5) is None
    assert frame_builder.input_problem({**fresh, 'tf': None}, (0, 0, False), 0.5) == 'no_tf'
    assert frame_builder.input_problem({**fresh, 'odom': 0.6}, (0, 0, False), 0.5) == 'no_odom'
    assert frame_builder.input_problem({**fresh, 'people': 0.9}, None, 0.5) == 'no_people'
    assert frame_builder.input_problem(fresh, None, 0.5) == 'no_waypoint'


def test_waypoint_goal_index_past_end_is_none():
    waypoints = [(1.0, 2.0, False), (3.0, 4.0, True)]
    assert frame_builder.waypoint_goal(waypoints, 1) == (3.0, 4.0, True)
    assert frame_builder.waypoint_goal(waypoints, 2) is None  # completed: index == 개수
    assert frame_builder.waypoint_goal(waypoints, None) is None


def test_load_waypoints_reads_stop_type(tmp_path):
    path = tmp_path / 'w.yaml'
    path.write_text('waypoints:\n  - {name: A, type: pass, x: 1, y: 2, yaw: 0, wait_sec: 0}\n'
                    '  - {name: B, type: stop, x: 3.5, y: 0, yaw: 90, wait_sec: 0}\n')
    assert frame_builder.load_waypoints(str(path)) == [(1.0, 2.0, False), (3.5, 0.0, True)]


def test_assemble_frame_goal_and_velocity_slots():
    settings = frame_builder.FrameSettings()
    scan = ([2.0] * 360, 0.0, 2 * math.pi / 360)
    # 로봇 (0, 0, 0), 목표 (0, 2.5) = 왼쪽 2.5 m, 정지 경유점
    frame = frame_builder.assemble_frame(scan, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
                                         (0.0, 2.5, True), (0.25, -0.4), [], settings)
    goal = frame[features.SCAN_BINS:features.SCAN_BINS + features.GOAL_SIZE]
    np.testing.assert_allclose(goal, [0.5, 1.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(frame[76:78], [0.5, -0.5])
    np.testing.assert_allclose(frame[:features.SCAN_BINS], 2.0 / 6.0)


def test_push_and_stack_keeps_last_three():
    history = []
    for value in range(5):
        x = frame_builder.push_and_stack(history, np.full(features.FRAME_SIZE, float(value)))
    assert len(history) == features.STACK_FRAMES
    assert x[0] == 2.0 and x[-1] == 4.0


def called_functions(file_name):
    """파일에서 frame_builder.<함수>(...)로 부르는 함수 이름들."""
    with open(os.path.join(PACKAGE_DIR, file_name), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    return {node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 'frame_builder'}


def test_node_and_dataset_use_the_same_assembly_functions():
    # policy_node는 rclpy를 import해서 여기서 불러올 수 없어 소스에서 호출을 찾는다
    shared = {'assemble_frame', 'push_and_stack', 'input_problem', 'waypoint_goal',
              'load_waypoints', 'yaw_from_quaternion', 'settings_from_dict'}
    assert shared <= called_functions('policy_node.py')
    assert shared <= called_functions('dataset.py')


def test_same_inputs_give_same_vector_from_dataset_path_and_direct_call():
    streams = dataset.BagStreams(start_time=0.0, end_time=1.0)
    streams.tf_static[('map', 'odom')] = (1.0, 0.0, 0.0)
    streams.tf[('odom', 'base_footprint')] = dataset.Series([(0.9, (0.5, 0.5, 0.3))])
    streams.odom = dataset.Series([(0.95, (0.5, 0.5, 0.2, 0.1))])
    streams.patrol = dataset.Series([(0.0, ('patrolling', 0))])
    streams.predictions = dataset.Series([(0.9, [(2.0, 1.0, 0.1, 0.0)])])
    cfg = dict(dataset.DEFAULTS)
    inputs = dataset.inputs_at(streams, 1.0, [(4.0, 2.0, False)], cfg)
    scan = ([1.5] * 100, -math.pi, 2 * math.pi / 100)
    settings = frame_builder.FrameSettings()
    via_dataset = frame_builder.assemble_frame(scan, inputs['pose_map'], inputs['pose_odom'],
                                               inputs['goal'], inputs['velocity'],
                                               inputs['people'], settings)
    direct = frame_builder.assemble_frame(scan, (1.5, 0.5, 0.3), (0.5, 0.5, 0.3),
                                          (4.0, 2.0, False), (0.2, 0.1),
                                          [(2.0, 1.0, 0.1, 0.0)], settings)
    np.testing.assert_array_equal(via_dataset, direct)
