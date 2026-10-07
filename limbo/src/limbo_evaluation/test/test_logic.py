"""ROS 없이 도는 사람 정답 위치·평가 지표·CSV 테스트."""

import csv
import math

from limbo_evaluation import actors, csv_log, goal_metrics
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


def test_csv_header_written_once(tmp_path):
    path = tmp_path / 'out' / 'nav.csv'
    csv_log.append_row(str(path), {'a': 1, 'b': 2})
    csv_log.append_row(str(path), {'a': 3, 'b': 4})
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert rows == [{'a': '1', 'b': '2'}, {'a': '3', 'b': '4'}]
