"""한 바퀴 지표 단위 테스트. 가짜 궤적은 0.1 s 간격."""

import math
import time

from limbo_imitation import metrics
import pytest

DT = 0.1


def straight_run(seconds=10.0, speed=0.5):
    """막힘 없이 직진하며 완주한 바퀴."""
    log = metrics.RunLog(start_time=0.0, end_time=seconds)
    steps = int(round(seconds / DT))
    for i in range(steps):
        t = i * DT
        log.odom.append((t, speed * t, 0.0, speed, 0.0))
        log.cmd.append((t, speed, 0.0))
        log.cmd_out.append((t, speed, 0.0))
        log.scan_edge.append((t, 1.0))
        log.person_dist.append((t, 3.0))
    log.patrol_states = [(0.0, 'patrolling'), (seconds, 'completed')]
    log.drive_modes = [(0.0, 'policy', 'policy_assist')]
    return log


def test_clean_run_passes():
    m = metrics.compute_metrics(straight_run())
    assert m['collisions'] == 0
    assert m['completed'] is True
    assert m['distance'] == pytest.approx(0.5 * 9.9)
    assert m['stuck_time'] == 0
    assert metrics.passed(m, {'personal_space': 0.5}) == (True, [])


def test_collision_monitor_stop_and_close_scan_each_count_once():
    log = straight_run()
    log.monitor_states = [(2.0, 0), (3.0, metrics.COLLISION_MONITOR_STOP), (3.5, 0)]
    log.scan_edge[50] = (5.0, 0.02)  # 발판 가장자리에서 2 cm(collision_edge_distance 3 cm 안)
    log.scan_edge[51] = (5.1, 0.01)
    m = metrics.compute_metrics(log)
    assert (m['collision_monitor_stops'], m['scan_collisions'], m['collisions']) == (1, 1, 2)
    ok, reasons = metrics.passed(m, {'personal_space': 0.5})
    assert not ok and reasons == ['collisions 2']


def test_personal_space_time_and_min_distance():
    log = straight_run()
    for i in range(20, 40):  # 2.0~4.0 s 동안 0.4 m
        log.person_dist[i] = (i * DT, 0.4)
    m = metrics.compute_metrics(log, {'personal_space': 0.5})
    assert m['personal_space_time'] == pytest.approx(2.0)
    assert m['min_person_dist_moving'] == pytest.approx(0.4)
    assert not metrics.passed(m, {'personal_space': 0.5})[0]


def test_person_walking_up_to_stopped_robot_is_not_counted():
    log = straight_run()
    for i in range(20, 40):  # 2.0~4.0 s: 로봇은 서 있고 사람이 0.3 m까지 다가옴(손님)
        t, x, y, _, w = log.odom[i]
        log.odom[i] = (t, x, y, 0.0, w)
        log.cmd[i] = (t, 0.0, 0.0)
        log.cmd_out[i] = (t, 0.0, 0.0)
        log.person_dist[i] = (t, 0.3)
    m = metrics.compute_metrics(log, {'personal_space': 0.5})
    assert m['min_person_dist'] == pytest.approx(0.3)  # 참고용 전체 최소 거리
    assert m['min_person_dist_moving'] == pytest.approx(3.0)
    assert m['personal_space_time'] == 0
    assert metrics.passed(m, {'personal_space': 0.5}) == (True, [])
    assert metrics.bad_intervals(log) == []


def test_no_people_gives_infinite_min_distance():
    log = straight_run()
    log.person_dist = []
    assert math.isinf(metrics.compute_metrics(log)['min_person_dist'])


def test_stuck_time_counts_only_long_mismatch():
    log = straight_run()
    for i in range(30, 60):  # 3.0~6.0 s: 명령 0.5인데 odom 0
        t, x, y, _, w = log.odom[i]
        log.odom[i] = (t, x, y, 0.0, w)
    log.odom[80] = (8.0, 4.0, 0.0, 0.0, 0.0)  # 0.1 s짜리 어긋남은 출발 지연으로 봄
    m = metrics.compute_metrics(log, {'stuck_min_duration': 1.0})
    assert m['stuck_time'] == pytest.approx(3.0)
    assert 'stuck 3.0 s' in metrics.passed(m, {'personal_space': 0.5})[1]


def test_interventions_only_in_policy_assist():
    log = straight_run()
    log.drive_modes = [(0.0, 'policy', 'policy_assist'), (2.0, 'teleop', 'policy_assist'),
                       (3.0, 'policy', 'policy_assist'), (5.0, 'teleop', 'policy_assist'),
                       (5.5, 'nav', 'policy_assist'), (6.0, 'policy', 'policy_assist')]
    m = metrics.compute_metrics(log)
    assert m['intervention_count'] == 2
    assert m['intervention_time'] == pytest.approx(1.5)
    assert m['nav_fallback_count'] == 1
    log.drive_modes = [(0.0, 'teleop', 'manual')]
    assert metrics.compute_metrics(log)['intervention_count'] == 0


def test_wobble_ratio():
    cmd = [(0.0, 0.3, 0.0), (0.1, 0.3, 0.8), (0.2, 0.3, 0.9), (0.3, 0.3, 0.0)]
    assert metrics.wobble_ratio(cmd, 0.5) == pytest.approx(2 / 3)


def test_bad_intervals_merge_collision_margin_personal_space_and_clipping():
    log = straight_run(seconds=30.0)
    log.monitor_states = [(10.0, metrics.COLLISION_MONITOR_STOP), (11.0, 0)]
    for i in range(130, 140):  # 13.0~14.0 s 사람 0.3 m: 충돌 여유(16 s까지)와 겹쳐 합쳐진다
        log.person_dist[i] = (i * DT, 0.3)
    log.monitor_states += [(25.0, 3), (25.5, 0)]  # 25.0~25.5 s collision_monitor approach(속도를 깎음)
    result = metrics.bad_intervals(log, {'collision_margin': 5.0})
    assert result == [(5.0, 16.0), (pytest.approx(25.0), pytest.approx(25.5))]


def test_metrics_row_has_all_columns():
    row = metrics.metrics_row(metrics.compute_metrics(straight_run()), {'personal_space': 0.5})
    assert list(row) == metrics.ROW_COLUMNS
    assert row['passed'] is True and row['fail_reasons'] == ''


FOOTPRINT = '[[0.25, 0.295], [0.25, -0.295], [-0.25, -0.295], [-0.25, 0.295]]'


def test_scan_edge_distance_from_footprint_edge_ignores_points_inside():
    settings = {**metrics.DEFAULT_SETTINGS, 'footprint': FOOTPRINT}
    # 스캔 프레임 = base. 정면 0.27 m(가장자리에서 2 cm), 왼쪽 0.10 m(발판 안쪽, 자기 몸 점), 무효 값
    ranges = [0.27, 0.10, math.inf, math.nan]
    scan = (ranges, 0.0, math.pi / 2, 0.1, 20.0)
    assert metrics.scan_edge_distance(scan, (0.0, 0.0, 0.0), settings) == pytest.approx(0.02)
    # 라이다가 base에 대해 +90° 돌아 있으면 스캔 0°는 base 왼쪽: 0.27 m 점은 옆면(0.295) 안쪽이라 무시
    assert math.isinf(metrics.scan_edge_distance(scan, (0.0, 0.0, math.pi / 2), settings))


def test_scan_collision_counts_only_while_moving():
    log = straight_run()
    for i in range(20, 40):  # 2.0~4.0 s: 로봇이 서 있는데 가장자리 1 cm 점(손님이 쓰레기를 넣음)
        t, x, y, _, w = log.odom[i]
        log.odom[i] = (t, x, y, 0.0, w)
        log.scan_edge[i] = (t, 0.01)
    assert metrics.compute_metrics(log)['scan_collisions'] == 0
    log.scan_edge[60] = (6.0, 0.01)  # 움직이는 중이면 센다
    assert metrics.compute_metrics(log)['scan_collisions'] == 1


def test_clipping_comes_from_collision_monitor_state_not_command_timing():
    log = straight_run()
    for i in range(1, len(log.cmd_out)):  # 출력이 한 칸 앞 입력에서 나오는 것은 깎임이 아니다
        log.cmd[i] = (log.cmd[i][0], 0.5 + 0.01 * i, 0.0)
        log.cmd_out[i] = (log.cmd_out[i][0], log.cmd[i - 1][1], 0.0)
    assert metrics.clipped_intervals(log, metrics.DEFAULT_SETTINGS) == []


def test_manual_start_run_is_completed_by_driver():
    log = straight_run()
    log.patrol_states = []  # 수동 바퀴에는 /patrol/state가 없다
    log.start_reason = metrics.START_MANUAL
    m = metrics.compute_metrics(log)
    assert m['completed'] == metrics.COMPLETED_MANUAL
    assert metrics.passed(m, {'personal_space': 0.5}) == (True, [])


def test_button_run_is_completed_by_driver():
    log = straight_run()
    log.patrol_states = []
    log.start_reason = metrics.START_BUTTON  # 패드 버튼으로 시작·끝낸 바퀴
    m = metrics.compute_metrics(log)
    assert m['completed'] == metrics.COMPLETED_MANUAL
    assert metrics.passed(m, {'personal_space': 0.5}) == (True, [])


def test_patrol_run_without_completed_state_fails():
    log = straight_run()
    log.patrol_states = [(0.0, 'patrolling')]
    log.start_reason = 'patrolling'
    m = metrics.compute_metrics(log)
    assert m['completed'] is False
    assert metrics.passed(m, {'personal_space': 0.5}) == (False, ['not completed'])


def test_metrics_stay_fast_on_long_run():
    """4~5분 바퀴(odom 30 Hz)의 지표가 1 s 안에. 종료가 지표 계산에 묶이지 않게."""
    log = straight_run(seconds=300.0, speed=0.5)
    start = time.monotonic()
    metrics.compute_metrics(log)
    metrics.bad_intervals(log)
    assert time.monotonic() - start < 1.0
