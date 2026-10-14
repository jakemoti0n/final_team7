"""ROS 없이 도는 사람 정답 위치·평가 지표·CSV 테스트."""

import csv
import math

from limbo_evaluation import actors, csv_log, goal_metrics, obstacles
import pytest

SDF = """
<world name="w">
    <actor name="walker">
      <script>
        <loop>true</loop><delay_start>0.0</delay_start><auto_start>true</auto_start>
        <trajectory id="0" type="walk">
          <waypoint><time>0.00</time><pose>0.00 0.00 1.0 0 0 0</pose></waypoint>
          <waypoint><time>10.00</time><pose>10.00 0.00 1.0 0 0 0</pose></waypoint>
          <waypoint><time>14.00</time><pose>10.00 0.00 1.0 0 0 0</pose></waypoint>
        </trajectory>
      </script>
    </actor>
    <actor name="delayed">
      <script>
        <loop>true</loop>
        <delay_start>2.0</delay_start>
        <trajectory id="0" type="walk">
          <waypoint>
            <time>0.00</time>
            <pose>0.00 5.00 1.0 0 0 0</pose>
          </waypoint>
          <waypoint>
            <time>4.00</time>
            <pose>0.00 9.00 1.0 0 0 0</pose>
          </waypoint>
        </trajectory>
      </script>
    </actor>
    <actor name="no_script"><skin><filename>x.dae</filename></skin></actor>
    <model name="obstacle_box">
      <static>true</static>
      <pose>2.00 0.00 0.050 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>0.4 0.2 0.1</size></box></geometry>
        </collision>
      </link>
    </model>
    <model name="wall"><pose>9 9 0 0 0 0</pose><link name="l"><collision name="c">
      <geometry><box><size>1 1 1</size></box></geometry></collision></link></model>
</world>
"""


@pytest.fixture
def people():
    return actors.parse_actor_trajectories(SDF)


def test_parse_skips_actor_without_waypoints(people):
    assert set(people) == {'walker', 'delayed'}
    assert people['delayed'].delay == 2.0


def test_position_moves_then_stops(people):
    walker = people['walker']
    assert actors.position_at(walker, 5.0) == pytest.approx((5.0, 0.0))
    # 10~14초는 같은 자리에 멈춰 있다
    assert actors.position_at(walker, 12.0) == pytest.approx((10.0, 0.0))


def test_position_loops(people):
    walker = people['walker']
    assert actors.position_at(walker, 14.0 + 5.0) == pytest.approx((5.0, 0.0))


def test_delay_repeats_every_loop(people):
    delayed = people['delayed']
    # 한 주기 = 지연 2초 + 걷기 4초. 지연 동안은 첫 위치에서 기다린다
    assert actors.position_at(delayed, 1.0) == pytest.approx((0.0, 5.0))
    assert actors.position_at(delayed, 4.0) == pytest.approx((0.0, 7.0))
    assert actors.position_at(delayed, 6.0 + 1.0) == pytest.approx((0.0, 5.0))


def test_nearest_person(people):
    name, distance = actors.nearest_person(people, 5.0, 5.0, 1.0)
    assert name == 'walker'
    assert distance == pytest.approx(1.0)
    assert actors.nearest_person({}, 0.0, 0.0, 0.0) == ('', math.inf)


def test_metrics_path_and_personal_space():
    m = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig(personal_space=0.5))
    m.add_truth(10.0, 0.0, 0.0, 'a', 2.0)
    m.add_truth(11.0, 1.0, 0.0, 'a', 0.4)   # 이 1초 동안 개인 공간 안
    m.add_truth(12.0, 1.0, 1.0, 'b', 0.3)   # 이 1초도
    m.add_truth(13.0, 1.0, 2.0, 'b', 1.0)
    m.add_localization_error(0.1)
    m.add_localization_error(0.3)
    row = m.row('SUCCEEDED')

    assert row['duration_s'] == 3.0
    assert row['path_length_m'] == 3.0
    assert row['mean_speed_mps'] == 1.0
    assert row['personal_space_time_s'] == 2.0
    assert (row['min_person_distance_m'], row['nearest_person']) == (0.3, 'b')
    assert (row['localization_error_mean_m'], row['localization_error_max_m']) == (0.2, 0.3)
    assert (row['start_x'], row['end_y']) == (0.0, 2.0)


def test_metrics_without_data_still_makes_row():
    row = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig()).row('ABORTED')
    assert row['status'] == 'ABORTED'
    assert row['duration_s'] == 0.0
    assert row['localization_error_max_m'] == ''


def test_nearest_in_time():
    times = [1.0, 2.0, 3.0]
    values = ['a', 'b', 'c']
    assert goal_metrics.nearest_in_time(times, values, 2.4) == 'b'
    assert goal_metrics.nearest_in_time(times, values, 2.6) == 'c'
    assert goal_metrics.nearest_in_time(times, values, 9.0) == 'c'
    assert goal_metrics.nearest_in_time([], [], 1.0) is None


def test_parse_only_obstacle_boxes():
    boxes = obstacles.parse_boxes(SDF)
    assert [(b.name, b.x, b.half_x, b.half_y) for b in boxes] == [('obstacle_box', 2.0, 0.2, 0.1)]


def test_obstacle_distance_from_robot_edge():
    boxes = obstacles.parse_boxes(SDF)
    # 로봇 중심 (1.0, 0), 앞 모서리 1.225 → 상자 앞면 1.8까지 0.575m
    name, distance = obstacles.nearest_box(boxes, 1.0, 0.0, 0.0, 0.225)
    assert name == 'obstacle_box'
    assert distance == pytest.approx(0.575)
    # 45° 돌면 앞 꼭짓점이 0.318m 나와서 더 가까워진다
    _, turned = obstacles.nearest_box(boxes, 1.0, 0.0, math.pi / 4, 0.225)
    assert turned == pytest.approx(0.8 - 0.225 * math.sqrt(2), abs=0.02)


def test_obstacle_touching_or_inside_is_zero():
    boxes = obstacles.parse_boxes(SDF)
    assert obstacles.nearest_box(boxes, 1.6, 0.0, 0.0, 0.225)[1] == 0.0
    # 작은 상자가 로봇 아래로 완전히 들어와도 닿은 것
    assert obstacles.nearest_box(boxes, 2.0, 0.0, 0.0, 0.225)[1] == 0.0
    assert obstacles.nearest_box([], 0.0, 0.0, 0.0, 0.225) == ('', math.inf)


def test_metrics_obstacle_contact_time():
    m = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig())
    m.add_obstacle(0.05, 'a', 0.3)
    m.add_obstacle(0.05, 'a', 0.0)
    m.add_obstacle(0.05, 'a', 0.0)
    row = m.row('SUCCEEDED')
    assert row['min_obstacle_distance_m'] == 0.0
    assert row['nearest_obstacle'] == 'a'
    assert row['obstacle_contact_time_s'] == 0.1


def test_csv_header_written_once(tmp_path):
    path = tmp_path / 'out' / 'nav.csv'
    csv_log.append_row(str(path), {'a': 1, 'b': 2})
    csv_log.append_row(str(path), {'a': 3, 'b': 4})
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert rows == [{'a': '1', 'b': '2'}, {'a': '3', 'b': '4'}]


def test_metrics_collision_and_stopped_time_split_by_person():
    m = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig(
        collision_distance=0.3, near_person_distance=1.5, stop_speed=0.05))
    m.add_truth(0.0, 0.0, 0.0, 'a', 3.0)
    m.add_truth(1.0, 0.5, 0.0, 'a', 2.0)   # 0.5 m/s 이동, 멈춤 아님
    m.add_truth(2.0, 0.5, 0.0, 'a', 1.0)   # 멈춤, 사람 1.5 m 안 → 사람 때문에 멈춤
    m.add_truth(3.0, 0.5, 0.0, 'a', 0.2)   # 멈춤 + 사람과 겹침(충돌)
    m.add_truth(4.0, 0.51, 0.0, 'a', 2.0)  # 0.01 m/s, 사람 없음 → 막혀서 멈춤
    row = m.row('SUCCEEDED')

    assert row['person_collision'] == 1
    assert row['person_collision_time_s'] == 1.0
    assert row['stopped_time_s'] == 3.0
    assert row['stopped_near_person_s'] == 2.0
    assert row['stopped_other_s'] == 1.0


def test_metrics_no_collision_when_person_far():
    m = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig())
    m.add_truth(0.0, 0.0, 0.0, 'a', 0.4)
    m.add_truth(1.0, 1.0, 0.0, 'a', 0.4)
    row = m.row('SUCCEEDED')
    assert (row['person_collision'], row['person_collision_time_s']) == (0, 0.0)
    assert row['stopped_time_s'] == 0.0


def test_sample_by_spacing_keeps_first_and_spaced_points():
    points = [(0.0, 0.0), (0.05, 0.0), (0.1, 0.0), (0.25, 0.0), (0.3, 0.0), (0.5, 0.0)]
    assert goal_metrics.sample_by_spacing(points, 0.2) == [(0.0, 0.0), (0.25, 0.0), (0.5, 0.0)]
    assert goal_metrics.sample_by_spacing([], 0.2) == []


def test_plan_deviation_is_max_distance_from_reference():
    reference = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    assert goal_metrics.plan_deviation([(0.0, 0.0), (1.0, 0.5)], reference) == pytest.approx(0.5)
    # 같은 경로의 뒷부분만 남아도 벗어난 게 아니다
    assert goal_metrics.plan_deviation([(1.0, 0.0), (2.0, 0.0)], reference) == 0.0


def test_metrics_counts_plan_changes_only_when_path_moves():
    m = goal_metrics.GoalMetrics(goal_metrics.MetricsConfig(
        plan_change_distance=0.3, plan_sample_spacing=0.2))
    straight = [(x / 10, 0.0) for x in range(0, 21)]          # (0,0)→(2,0)
    detour = [(x / 10, 0.0 if x < 5 or x > 15 else 0.6) for x in range(0, 21)]
    m.add_plan(straight)
    m.add_plan(straight[5:])   # 지나온 만큼 짧아진 같은 경로
    m.add_plan(detour)         # 0.6 m 돌아감 → 바뀜
    m.add_plan(detour)
    m.add_plan([])             # 빈 경로는 세지 않는다
    row = m.row('SUCCEEDED')
    assert (row['plan_updates'], row['plan_changes']) == (4, 1)
