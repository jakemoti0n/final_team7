"""사람 기다리기 상태 기계 (설계 전제 2-7)."""

from limbo_perception import person_wait as pw

STANDING_IN_ZONE = (1.0, 0.0, 0.0, 0.0)      # 범퍼 앞에 서서 쓰레기를 버리는 손님
WALKING_IN_ZONE = (1.0, 0.0, 0.0, 0.8)       # 같은 자리에서 옆으로 걷기 시작함


def _ready_machine():
    machine = pw.PersonWait()
    machine.on_tick(0.0, [], ready=True)
    return machine


def _blocked_machine():
    """준비된 뒤 로봇이 2 s 넘게 서 있는 상태. 구역 안에 서 있는 사람 때문에 기다릴 수 있는 전제(막힘)."""
    machine = pw.PersonWait()
    machine.on_tick(-3.0, [], ready=True)
    for i in range(1, 31):
        machine.on_tick(-3.0 + i * 0.1, [], ready=True, robot_speed=0.0)
    return machine


def _run(machine, start, end, tracks, dt=0.1, **kwargs):
    """start부터 end 직전까지 같은 트랙으로 틱을 돌리고 모든 출력을 돌려준다."""
    statuses = []
    steps = int(round((end - start) / dt))
    for i in range(steps):
        statuses.append(machine.on_tick(start + i * dt, tracks, ready=True, **kwargs))
    return statuses


def test_not_ready_outputs_nothing_until_ready():
    """시작 직후 자기 몸을 사람으로 보지 않도록, 준비 전에는 트랙이 있어도 기다리지 않는다."""
    machine = pw.PersonWait()
    status = machine.on_tick(0.0, [STANDING_IN_ZONE], ready=False)
    assert status.state == pw.NOT_READY and status.wait is False and status.reason == 'not_ready'
    status = machine.on_tick(0.1, [], ready=True)
    assert status.state == pw.DRIVING and status.wait is False


def test_person_walking_straight_at_robot_makes_it_wait():
    """진로 위로 다가오는 사람은 손님이므로 멈춰 기다린다(2-1)."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(2.0, 0.0, -0.5, 0.0)], ready=True)
    assert status.state == pw.WAITING and status.wait is True and status.reason == 'approaching'


def test_person_passing_beside_keeps_driving():
    """옆으로 1 m 떨어져 지나가는 사람(최근접 1.0 m > 0.6 m)은 손님이 아니다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(2.0, 1.0, -0.8, 0.0)], ready=True)
    assert status.state == pw.DRIVING and status.wait is False


def _stall(machine, t0, tracks, sec=2.0):
    """로봇이 sec 동안 서 있는 상황을 흉내 낸다(속도 0). 마지막 상태를 돌려준다."""
    status = None
    for i in range(int(sec * 10) + 1):
        status = machine.on_tick(t0 + i * 0.1, tracks, ready=True, robot_speed=0.0)
    return status


def test_person_standing_in_zone_waits_only_when_robot_is_blocked():
    """서 있는 사람은 그 자체로 손님이 아니다. 로봇이 실제로 막혔을 때(속도 0이 2 s)만 기다린다(2-2)."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [STANDING_IN_ZONE], ready=True, robot_speed=0.3)
    assert status.state == pw.DRIVING and status.tracks_in_zone == 1
    status = _stall(machine, 0.2, [STANDING_IN_ZONE])
    assert status.state == pw.WAITING and status.reason == 'blocked_in_zone'


def test_person_standing_beside_path_does_not_stop_a_moving_robot():
    """벽 옆에 서 있는 사람 옆을 지나갈 때(구역 가장자리에 걸려도) 로봇이 움직이는 한 기다리지 않는다."""
    machine = _ready_machine()
    edge = (1.4, -0.5, 0.0, 0.0)
    statuses = _run(machine, 0.1, 5.0, [edge], robot_speed=0.25)
    assert {s.state for s in statuses} == {pw.DRIVING}


def test_unknown_robot_speed_never_waits_for_standing_person():
    """오도메트리가 없으면 막힘을 모르므로 서 있는 사람 때문에 기다리지 않는다(다가옴은 그대로)."""
    machine = _ready_machine()
    statuses = _run(machine, 0.1, 5.0, [STANDING_IN_ZONE])
    assert {s.state for s in statuses} == {pw.DRIVING}
    assert machine.on_tick(5.1, [(2.0, 0.0, -0.5, 0.0)], ready=True).state == pw.WAITING


def test_leaves_zone_then_drives_after_release_sec():
    """구역이 빈 뒤 release_sec(0.5 s) 동안은 기다리고, 그 뒤 다시 출발한다."""
    machine = _ready_machine()
    _stall(machine, 1.0, [STANDING_IN_ZONE])
    gone = [(1.0, 2.0, 0.0, 0.0)]                   # 옆으로 비켜 섬
    assert machine.on_tick(2.0, gone, ready=True).state == pw.WAITING
    assert machine.on_tick(2.4, gone, ready=True).state == pw.WAITING
    status = machine.on_tick(2.5, gone, ready=True)
    assert status.state == pw.DRIVING and status.reason == 'zone_clear'


def test_margin_prevents_chatter_at_zone_edge():
    """경계 바로 밖(1.6 m)을 오가는 사람 때문에 대기·주행이 번갈아 바뀌지 않는다."""
    machine = _blocked_machine()
    machine.on_tick(0.1, [(1.4, 0.0, 0.0, 0.0)], ready=True, robot_speed=0.0)
    states = [machine.on_tick(0.2 + 0.1 * i, [(1.4 if i % 2 else 1.6, 0.0, 0.0, 0.0)],
                              ready=True).state for i in range(30)]
    assert set(states) == {pw.WAITING}
    assert len(machine.transitions) == 2           # ready, blocked_in_zone 뿐


def test_no_pull_over_spot_keeps_waiting_and_alarms_every_period():
    """비켜설 자리가 없으면 상한 없이 계속 기다리고, 경보는 30 s마다 한 틱만 낸다."""
    machine = _blocked_machine()
    statuses = _run(machine, 1.0, 101.0, [STANDING_IN_ZONE], robot_speed=0.0)
    assert {s.state for s in statuses} == {pw.WAITING}
    alarm_times = [1.0 + i * 0.1 for i, s in enumerate(statuses) if s.alarm]
    assert len(alarm_times) == 3                   # 서비스 시간 15 s가 끝난 순간부터 30 s 간격
    assert abs(alarm_times[0] - 16.0) < 0.05
    assert all(abs(b - a - 30.0) < 0.15 for a, b in zip(alarm_times, alarm_times[1:]))
    first_alarm = statuses[150]
    assert first_alarm.reason == 'no_pull_over_spot_15s'
    assert statuses[151].alarm is False and statuses[151].reason == 'no_pull_over_spot'


def test_service_time_with_spot_pulls_over():
    """손님이 서 있는 채 15 s가 지나고 자리가 있으면 비켜선다."""
    machine = _blocked_machine()
    statuses = _run(machine, 1.0, 16.1, [STANDING_IN_ZONE],
                    pull_over_available=True, robot_speed=0.0)
    assert statuses[-2].state == pw.WAITING        # 14.9 s
    assert statuses[-2].stationary_sec > 14.8
    assert statuses[-1].state == pw.PULL_OVER and statuses[-1].reason == 'service_done'


def test_person_moving_during_pull_over_aborts_it():
    """비켜서는 중 손님이 움직이면 서로 피하는 마찰을 막으려 즉시 멈추고 다시 기다린다."""
    machine = _blocked_machine()
    _run(machine, 1.0, 16.1, [STANDING_IN_ZONE], pull_over_available=True, robot_speed=0.0)
    assert machine.state == pw.PULL_OVER
    status = machine.on_tick(17.0, [WALKING_IN_ZONE], ready=True, pull_over_available=True)
    assert status.state == pw.WAITING and status.abort_pull_over is True
    assert status.stationary_sec == 0.0           # 서비스 시간은 처음부터 다시 잰다


def test_pull_over_done_drives_on():
    """비켜서기가 끝나면 다시 주행한다."""
    machine = _blocked_machine()
    _run(machine, 1.0, 16.1, [STANDING_IN_ZONE], pull_over_available=True, robot_speed=0.0)
    status = machine.on_tick(20.0, [STANDING_IN_ZONE], ready=True, pull_over_done=True)
    assert status.state == pw.DRIVING and status.reason == 'pull_over_done'


def test_no_tracks_does_nothing_even_after_60_s():
    """트랙이 없으면 장애물이라 Nav2 몫이고, 시간이 지나도 이 모듈은 아무것도 바꾸지 않는다."""
    machine = _ready_machine()
    statuses = _run(machine, 0.1, 60.1, [])
    assert {s.state for s in statuses} == {pw.DRIVING}
    assert not any(s.wait or s.alarm for s in statuses)


def test_slow_track_is_not_approaching_but_counts_in_zone():
    """0.1 m/s는 검출 떨림과 구분이 안 되어 다가옴이 아니지만, 구역 안에서 로봇을 막으면 기다린다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(2.5, 0.0, -0.1, 0.0)], ready=True)
    assert status.state == pw.DRIVING
    status = _stall(machine, 0.2, [(1.2, 0.0, -0.1, 0.0)])
    assert status.state == pw.WAITING and status.reason == 'blocked_in_zone'


def test_approach_beyond_camera_range_is_ignored():
    """4 m 밖은 카메라를 믿지 못하는 거리라 다가와도 아직 멈추지 않는다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(4.0, 0.0, -1.0, 0.0)], ready=True)
    assert status.state == pw.DRIVING


def test_approach_at_camera_range_waits():
    """하반신 모델은 3.0 m까지 믿을 수 있어 그 거리에서 다가오면 기다린다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(3.0, 0.0, -1.0, 0.0)], ready=True)
    assert status.state == pw.WAITING and status.reason == 'approaching'


def test_transitions_are_recorded_for_logging():
    """노드가 "왜 멈췄나/갔나"를 한 줄로 찍을 수 있게 전이(시각·전·후·사유)가 순서대로 남는다."""
    machine = pw.PersonWait()
    machine.on_tick(0.0, [], ready=False)
    machine.on_tick(0.1, [], ready=True)
    for i in range(21):                                   # 로봇이 2 s 서 있음(막힘)
        machine.on_tick(0.2 + i * 0.1, [], ready=True, robot_speed=0.0)
    machine.on_tick(2.3, [STANDING_IN_ZONE], ready=True, robot_speed=0.0)
    machine.on_tick(3.0, [], ready=True)
    machine.on_tick(3.5, [], ready=True)
    machine.on_tick(4.0, [], ready=False)
    assert [(tr.t, tr.from_state, tr.to_state, tr.reason) for tr in machine.transitions] == [
        (0.1, pw.NOT_READY, pw.DRIVING, 'ready'),
        (2.3, pw.DRIVING, pw.WAITING, 'blocked_in_zone'),
        (3.5, pw.WAITING, pw.DRIVING, 'zone_clear'),
        (4.0, pw.DRIVING, pw.NOT_READY, 'not_ready'),
    ]


def test_speed_jitter_does_not_restart_service_time():
    """서 있는 손님 속도가 0.2~0.3 m/s로 떨리거나 0.3 이상이 1 s 안으로 튀어도 서비스 시간은 이어진다."""
    machine = _blocked_machine()
    _run(machine, 1.0, 6.0, [STANDING_IN_ZONE], robot_speed=0.0)
    _run(machine, 6.0, 8.0, [(1.0, 0.0, 0.25, 0.0)])     # 떨림: 정지 기준과 움직임 기준 사이
    _run(machine, 8.0, 8.5, [(1.0, 0.0, 0.5, 0.0)])      # 0.5 s 튐
    status = _run(machine, 8.5, 10.0, [STANDING_IN_ZONE])[-1]
    assert status.state == pw.WAITING and status.stationary_sec > 8.8
    statuses = _run(machine, 10.0, 11.5, [(1.0, 0.0, 0.5, 0.0)])   # 1 s 넘게 움직임 → 풀림
    assert statuses[-1].stationary_sec == 0.0


def test_guest_lost_by_camera_at_bumper_is_held_by_tof_until_tof_clears():
    """코앞 손님이 화면 밖으로 빠져 트랙이 끊겨도 ToF가 막혀 있으면 계속 기다리고(시간 제한 없음), ToF가 비면 바로 간다."""
    machine = _blocked_machine()
    _run(machine, 1.0, 3.0, [(0.4, 0.0, 0.0, 0.0)], robot_speed=0.0)   # 범퍼 0.4 m 앞 손님, 로봇은 막힘
    statuses = _run(machine, 3.0, 13.0, [], tof_blocked=True)      # 트랙 끊김, ToF 막힘 10 s
    assert {s.state for s in statuses} == {pw.WAITING}
    assert statuses[-1].reason == 'zone_track_lost_tof'
    status = machine.on_tick(13.0, [], ready=True, tof_blocked=False)
    assert status.state == pw.DRIVING and status.reason == 'tof_clear'


def test_tof_alone_does_not_hold_without_a_recent_close_track():
    """트랙이 멀리(1.0 m 밖) 있었거나 오래전이면 ToF 막힘은 장애물이라 기다림을 잇지 않는다(2-7 원칙 1)."""
    machine = _blocked_machine()
    _run(machine, 1.0, 3.0, [(1.3, 0.0, 0.0, 0.0)], robot_speed=0.0)   # 구역 안이지만 범퍼에서 1.3 m
    statuses = _run(machine, 3.0, 4.0, [], tof_blocked=True)
    assert statuses[-1].state == pw.DRIVING and machine.transitions[-1].reason == 'zone_clear'
