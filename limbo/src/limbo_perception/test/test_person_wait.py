"""사람 기다리기 상태 기계 (설계 전제 2-7)."""

from limbo_perception import person_wait as pw

STANDING_IN_ZONE = (1.0, 0.0, 0.0, 0.0)      # 범퍼 앞에 서서 쓰레기를 버리는 손님
WALKING_IN_ZONE = (1.0, 0.0, 0.0, 0.8)       # 같은 자리에서 옆으로 걷기 시작함


def _ready_machine():
    machine = pw.PersonWait()
    machine.on_tick(0.0, [], ready=True)
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


def test_person_standing_in_zone_makes_it_wait():
    """옆에서 와서 앞에 선 사람은 속도가 0이어도 구역 안이면 기다린다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [STANDING_IN_ZONE], ready=True)
    assert status.state == pw.WAITING and status.reason == 'in_zone'
    assert status.tracks_in_zone == 1


def test_leaves_zone_then_drives_after_release_sec():
    """구역이 빈 뒤 release_sec(0.5 s) 동안은 기다리고, 그 뒤 다시 출발한다."""
    machine = _ready_machine()
    machine.on_tick(1.0, [STANDING_IN_ZONE], ready=True)
    gone = [(1.0, 2.0, 0.0, 0.0)]                   # 옆으로 비켜 섬
    assert machine.on_tick(2.0, gone, ready=True).state == pw.WAITING
    assert machine.on_tick(2.4, gone, ready=True).state == pw.WAITING
    status = machine.on_tick(2.5, gone, ready=True)
    assert status.state == pw.DRIVING and status.reason == 'zone_clear'


def test_margin_prevents_chatter_at_zone_edge():
    """경계 바로 밖(1.6 m)을 오가는 사람 때문에 대기·주행이 번갈아 바뀌지 않는다."""
    machine = _ready_machine()
    machine.on_tick(0.1, [(1.4, 0.0, 0.0, 0.0)], ready=True)
    states = [machine.on_tick(0.2 + 0.1 * i, [(1.4 if i % 2 else 1.6, 0.0, 0.0, 0.0)],
                              ready=True).state for i in range(30)]
    assert set(states) == {pw.WAITING}
    assert len(machine.transitions) == 2           # ready, in_zone 뿐


def test_no_pull_over_spot_keeps_waiting_and_alarms_every_period():
    """비켜설 자리가 없으면 상한 없이 계속 기다리고, 경보는 30 s마다 한 틱만 낸다."""
    machine = _ready_machine()
    statuses = _run(machine, 1.0, 101.0, [STANDING_IN_ZONE])
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
    machine = _ready_machine()
    statuses = _run(machine, 1.0, 16.1, [STANDING_IN_ZONE], pull_over_available=True)
    assert statuses[-2].state == pw.WAITING        # 14.9 s
    assert statuses[-2].stationary_sec > 14.8
    assert statuses[-1].state == pw.PULL_OVER and statuses[-1].reason == 'service_done'


def test_person_moving_during_pull_over_aborts_it():
    """비켜서는 중 손님이 움직이면 서로 피하는 마찰을 막으려 즉시 멈추고 다시 기다린다."""
    machine = _ready_machine()
    _run(machine, 1.0, 16.1, [STANDING_IN_ZONE], pull_over_available=True)
    assert machine.state == pw.PULL_OVER
    status = machine.on_tick(17.0, [WALKING_IN_ZONE], ready=True, pull_over_available=True)
    assert status.state == pw.WAITING and status.abort_pull_over is True
    assert status.stationary_sec == 0.0           # 서비스 시간은 처음부터 다시 잰다


def test_pull_over_done_drives_on():
    """비켜서기가 끝나면 다시 주행한다."""
    machine = _ready_machine()
    _run(machine, 1.0, 16.1, [STANDING_IN_ZONE], pull_over_available=True)
    status = machine.on_tick(20.0, [STANDING_IN_ZONE], ready=True, pull_over_done=True)
    assert status.state == pw.DRIVING and status.reason == 'pull_over_done'


def test_no_tracks_does_nothing_even_after_60_s():
    """트랙이 없으면 장애물이라 Nav2 몫이고, 시간이 지나도 이 모듈은 아무것도 바꾸지 않는다."""
    machine = _ready_machine()
    statuses = _run(machine, 0.1, 60.1, [])
    assert {s.state for s in statuses} == {pw.DRIVING}
    assert not any(s.wait or s.alarm for s in statuses)


def test_slow_track_is_not_approaching_but_counts_in_zone():
    """0.1 m/s는 검출 떨림과 구분이 안 되어 다가옴이 아니지만, 구역 안에 있으면 기다린다."""
    machine = _ready_machine()
    status = machine.on_tick(0.1, [(2.5, 0.0, -0.1, 0.0)], ready=True)
    assert status.state == pw.DRIVING
    status = machine.on_tick(0.2, [(1.2, 0.0, -0.1, 0.0)], ready=True)
    assert status.state == pw.WAITING and status.reason == 'in_zone'


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
    """노드가 "왜 섰고 왜 갔는지"를 로그 한 줄로 남길 수 있게 전이를 모두 기록한다."""
    machine = pw.PersonWait()
    machine.on_tick(0.0, [], ready=False)
    machine.on_tick(0.1, [], ready=True)
    machine.on_tick(0.2, [STANDING_IN_ZONE], ready=True)
    machine.on_tick(1.0, [], ready=True)
    machine.on_tick(1.5, [], ready=True)
    machine.on_tick(2.0, [], ready=False)
    assert [(tr.t, tr.from_state, tr.to_state, tr.reason) for tr in machine.transitions] == [
        (0.1, pw.NOT_READY, pw.DRIVING, 'ready'),
        (0.2, pw.DRIVING, pw.WAITING, 'in_zone'),
        (1.5, pw.WAITING, pw.DRIVING, 'zone_clear'),
        (2.0, pw.DRIVING, pw.NOT_READY, 'not_ready'),
    ]
