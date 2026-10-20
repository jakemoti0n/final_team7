"""
사람 기다리기 상태 기계 (설계 전제 2-7, ROS 의존 없음).

기다릴지·갈지·비켜설지를 이 상태 기계 하나가 정한다. 근거는 사람 트랙뿐이다.
ToF·라이다 점은 사람인지 모르는 장애물 신호라 여기 들어오지 않는다(트랙이 없으면 Nav2 몫).
WAITING을 타이머로 끝내는 전이는 없다. 오래 기다리면 경보(alarm)만 낸다(2-7 원칙 2).

상태:
    NOT_READY  TF·지도·위치 추정 준비 전. 시작 직후 자기 몸을 사람으로 보는 일을 막는다.
    DRIVING    평소 주행.
    WAITING    손님 앞에 멈춰 기다림.
    PULL_OVER  손님이 서 있는 채 서비스 시간이 지나 옆으로 비켜서는 중(R6).
"""

from dataclasses import dataclass

from limbo_perception.geometry import closest_approach

NOT_READY = 'NOT_READY'
DRIVING = 'DRIVING'
WAITING = 'WAITING'
PULL_OVER = 'PULL_OVER'


@dataclass
class WaitConfig:
    robot_half_width: float = 0.30  # m, 로봇 몸통 반폭(v14)
    person_radius: float = 0.25     # m, 사람 몸 반경. 구역 반폭 = 로봇 반폭 + 사람 반경
    zone_length: float = 1.5        # m, 로봇 앞. ToF(0.5 m) 밖에 서서 쓰레기를 버리는 손님까지 덮는다
    zone_exit_margin: float = 0.2   # m, 나갈 때만 구역을 이만큼 넓힘. 경계에 선 사람 때문에 떨지 않게
    approach_range: float = 3.0     # m, 카메라(하반신 모델)가 사람을 믿을 만하게 보는 거리
    cpa_radius: float = 0.6         # m, 사람 진행 직선이 로봇에서 이 안을 지나면 진로 위로 다가옴(2-1)
    min_speed: float = 0.2          # m/s, 이보다 느리면 정지로 봄(걷기 ~1 m/s, 검출 떨림은 이보다 작음)
    moving_speed: float = 0.3       # m/s, 정지로 본 사람이 다시 움직인다고 볼 속도. min_speed와 틈을 둬 떨림에 안 흔들리게
    moving_hold_sec: float = 1.0    # s, moving_speed 이상이 이만큼 이어져야 정지가 풀림(튐으로 15 s를 다시 안 재게)
    release_sec: float = 0.5        # s, 구역이 빈 채 이만큼 지나면 출발. 긴 끊김은 트랙 grace 몫이라 짧게
    service_sec: float = 15.0       # s, T_service. 쓰레기를 버리는 데 드는 시간(2-7 결정 10-19)
    alarm_period_sec: float = 30.0  # s, 비켜설 자리 없이 계속 기다릴 때 경보 간격(2-7)
    # 코앞에 선 손님은 카메라 화면 밖(옆·아래)이라 트랙이 끊긴다(10-19 진단: ToF 0.5 m 안인데 박스 자체가 없는 프레임이 대부분).
    # 끊기기 직전 recent_track_sec 안에 구역 안 트랙이 track_lost_range 안에 있었고 지금 ToF가 막혔으면 그 손님으로 보고 계속
    # 기다린다. ToF만으로는 기다리기를 시작하지 못한다(2-7 원칙 1). ToF가 비면 바로 출발한다(타이머 없음)
    recent_track_sec: float = 3.0   # s
    track_lost_range: float = 1.0   # m, 범퍼에서. 카메라가 사람을 놓치기 시작하는 거리
    # 구역 안에 서 있는 사람은 그 자체로는 손님이 아니다(2-7: 손님은 다가오는 사람). 벽 옆에 서 있는 사람 옆을
    # 지나갈 때 구역 가장자리에 걸려 영영 기다린 일이 있었다(10-19 상자 벤치). 서 있는 사람 때문에 기다리는 것은
    # Nav2가 돌아가지 못해 로봇이 실제로 막혔을 때뿐이다(2-2 "사람 때문에 막힘"). 막힘 = 로봇 속도가 stall_speed
    # 미만으로 stall_sec 지속. Nav2 진전 검사(10 s)보다 먼저 걸려 사람 앞 복구를 막는다
    stall_speed: float = 0.05       # m/s
    stall_sec: float = 2.0          # s
    # 막혔을 때 "사람 때문인가"를 볼 구역은 진로 폭이 아니라 costmap이 사람을 막는 폭이다: 사람 치명 반경 + 팽창 반경
    # (nav2_params inflation_radius 0.45). 옆 0.75 m에 선 사람도 로봇을 막는데 진로 폭(0.55)만 보면 "사람 없음"으로 보고
    # 복구(회전)를 돌렸다(10-20 복도 시험, 2-2 위반). 다가옴 판정·평소 구역은 그대로
    blocked_zone_margin: float = 0.45  # m

    @property
    def zone_half_width(self):
        return self.robot_half_width + self.person_radius


@dataclass
class WaitStatus:
    state: str
    wait: bool
    reason: str
    tracks_in_zone: int = 0
    elapsed_sec: float = 0.0
    stationary_sec: float = 0.0
    alarm: bool = False
    abort_pull_over: bool = False


@dataclass
class Transition:
    t: float
    from_state: str
    to_state: str
    reason: str


def speed_of(track):
    _, _, vx, vy = track
    return (vx * vx + vy * vy) ** 0.5


def is_approaching(track, config):
    """사람 진행 직선이 로봇 가까이를 지나고, 충분히 빠르고, 카메라를 믿을 거리 안이면 다가옴."""
    rel_x, rel_y, vx, vy = track
    if speed_of(track) < config.min_speed:
        return False   # 서 있는 사람의 속도 방향은 검출 떨림이라 믿지 않는다
    if (rel_x * rel_x + rel_y * rel_y) ** 0.5 > config.approach_range:
        return False
    time_to_closest, distance = closest_approach(rel_x, rel_y, vx, vy)
    return time_to_closest > 0.0 and distance < config.cpa_radius


def in_zone(track, config, margin=0.0):
    """로봇 앞 구역 안인가. margin은 나갈 때 판정용 여유."""
    rel_x, rel_y, _, _ = track
    return (0.0 < rel_x <= config.zone_length + margin and
            abs(rel_y) <= config.zone_half_width + margin)


class PersonWait:
    """틱마다 on_tick을 부르면 WaitStatus를 돌려준다. 시각은 메시지 시각(초)."""

    def __init__(self, config=None):
        self.config = config or WaitConfig()
        self.state = NOT_READY
        self.state_since = None
        self.clear_since = None        # WAITING에서 구역이 비고 다가옴도 없기 시작한 시각
        self.stationary_since = None   # 구역 안 트랙이 전부 정지이기 시작한 시각
        self.moving_since = None       # 정지 중 구역 안 트랙이 moving_speed 이상으로 움직이기 시작한 시각
        self.close_track_at = None     # 구역 안 트랙이 track_lost_range 안에 마지막으로 보인 시각
        self.stalled_since = None      # 로봇 속도가 stall_speed 미만이기 시작한 시각(None이면 움직이는 중)
        self.blocked_entry = False     # 막혀서(blocked_in_zone) 기다리는 중이면 넓은 구역으로 본다
        self.tof_hold = False          # 트랙이 끊긴 손님을 ToF로 이어서 기다리는 중
        self.next_alarm_at = None
        self.transitions = []          # Transition 목록. 노드가 새로 생긴 것만 로그로 찍는다

    def on_tick(self, t, tracks, ready, pull_over_available=False, pull_over_done=False,
                tof_blocked=False, robot_speed=None):
        """
        tracks: 범퍼 앞 기준 (rel_x, rel_y, vx, vy) 목록(속도는 로봇 축, m/s).

        tof_blocked: ToF가 코앞(stop_distance 안)을 막힘으로 봄. 트랙이 끊긴 손님을 이어 기다릴 때만 쓴다.
        robot_speed: 로봇 전진 속도 크기(m/s). 서 있는 사람 때문에 막혔는지 볼 때만 쓴다. None이면 모름(= 안 막힘).
        """
        if self.state_since is None:
            self.state_since = t
        if not ready:
            if self.state != NOT_READY:
                self._go(t, NOT_READY, 'not_ready')
            return self._status(t, 'not_ready')
        if self.state == NOT_READY:
            self._go(t, DRIVING, 'ready')
            return self._status(t, 'ready')
        self._note_close_track(t, tracks)
        self._update_stall(t, robot_speed)
        if self.state == DRIVING:
            return self._tick_driving(t, tracks)
        if self.state == WAITING:
            return self._tick_waiting(t, tracks, pull_over_available, tof_blocked)
        return self._tick_pull_over(t, tracks, pull_over_done)

    def _tick_driving(self, t, tracks):
        c = self.config
        if any(is_approaching(track, c) for track in tracks):
            self._go(t, WAITING, 'approaching')
            return self._status(t, 'approaching', tracks)
        if any(in_zone(track, c, c.blocked_zone_margin) for track in tracks) and self._stalled(t):
            # 서 있는 사람이 (팽창까지 친) 구역 안에 있고 로봇이 실제로 막혔다: 사람 때문에 막힘(2-2) → 복구 대신 기다린다
            self._go(t, WAITING, 'blocked_in_zone')
            self.blocked_entry = True
            self._update_stationary(t, self._zone_tracks(tracks))   # 서비스 시간은 선 순간부터 잰다
            return self._status(t, 'blocked_in_zone', tracks)
        return self._status(t, 'clear', tracks)

    def _update_stall(self, t, robot_speed):
        if robot_speed is None or robot_speed > self.config.stall_speed:
            self.stalled_since = None
        elif self.stalled_since is None:
            self.stalled_since = t

    def _stalled(self, t):
        return self.stalled_since is not None and t - self.stalled_since >= self.config.stall_sec

    def _tick_waiting(self, t, tracks, pull_over_available, tof_blocked=False):
        c = self.config
        zone_tracks = self._zone_tracks(tracks)
        approaching = any(is_approaching(track, c) for track in tracks)
        if zone_tracks or approaching:
            self.clear_since = None
            self.tof_hold = False
        elif tof_blocked and (self.tof_hold or self._close_track_recent(t)):
            self.tof_hold, self.clear_since = True, None
            return self._status(t, 'zone_track_lost_tof', tracks)
        elif self.tof_hold:
            self._go(t, DRIVING, 'tof_clear')
            return self._status(t, 'tof_clear', tracks)
        elif self.clear_since is None:
            self.clear_since = t
        if self.clear_since is not None and t - self.clear_since >= c.release_sec:
            self._go(t, DRIVING, 'zone_clear')
            return self._status(t, 'zone_clear', tracks)

        self._update_stationary(t, zone_tracks)
        stationary_sec = self._stationary_sec(t)
        if stationary_sec < c.service_sec:
            reason = 'stationary' if zone_tracks and stationary_sec > 0.0 else (
                'in_zone' if zone_tracks else 'approaching' if approaching else 'releasing')
            return self._status(t, reason, tracks)
        if pull_over_available:
            self._go(t, PULL_OVER, 'service_done')
            return self._status(t, 'service_done', tracks)
        return self._keep_waiting_with_alarm(t, tracks, stationary_sec)

    def _keep_waiting_with_alarm(self, t, tracks, stationary_sec):
        """비켜설 자리가 없으면 계속 기다리고, 관제가 알도록 주기적으로 경보 한 틱을 낸다."""
        if self.next_alarm_at is None:
            self.next_alarm_at = t   # 서비스 시간이 끝난 순간 첫 경보
        status = self._status(t, 'no_pull_over_spot', tracks)
        if t >= self.next_alarm_at:
            self.next_alarm_at = t + self.config.alarm_period_sec
            status.alarm = True
            status.reason = f'no_pull_over_spot_{stationary_sec:.0f}s'
        return status

    def _tick_pull_over(self, t, tracks, pull_over_done):
        c = self.config
        zone_tracks = self._zone_tracks(tracks)
        if any(speed_of(track) >= c.min_speed for track in zone_tracks):
            # 버린 사람이 움직이기 시작하면 서로 피하는 마찰이 생기므로 비켜서기를 멈추고 다시 기다린다
            self._go(t, WAITING, 'person_moved')
            status = self._status(t, 'person_moved', tracks)
            status.abort_pull_over = True
            return status
        if pull_over_done:
            self._go(t, DRIVING, 'pull_over_done')
            return self._status(t, 'pull_over_done', tracks)
        return self._status(t, 'pulling_over', tracks)

    def _note_close_track(self, t, tracks):
        limit = self.config.track_lost_range
        zone_tracks = self._zone_tracks(tracks)
        if any((track[0] ** 2 + track[1] ** 2) ** 0.5 <= limit for track in zone_tracks):
            self.close_track_at = t

    def _close_track_recent(self, t):
        return (self.close_track_at is not None and
                t - self.close_track_at <= self.config.recent_track_sec)

    def _zone_tracks(self, tracks):
        """기다리는 중에는 넓힌 구역으로 본다(들어올 때보다 나갈 때 경계가 멀어야 안 떤다). 막혀서 기다리면 팽창 폭까지."""
        margin = self.config.zone_exit_margin
        if self.blocked_entry:
            margin = max(margin, self.config.blocked_zone_margin + self.config.zone_exit_margin)
        return [track for track in tracks
                if in_zone(track, self.config, margin)]

    def _update_stationary(self, t, zone_tracks):
        """
        서비스 시간(정지 시간)을 잰다. 정지 시작은 전부 min_speed 미만, 풀림은 moving_speed 이상이 moving_hold_sec 지속.

        구역이 잠깐 비는 것(검출 끊김)으로는 풀지 않는다. 정말 비면 release_sec 뒤 DRIVING으로 가며 _go가 지운다.
        """
        c = self.config
        if self.stationary_since is None:
            if zone_tracks and all(speed_of(track) < c.min_speed for track in zone_tracks):
                self.stationary_since, self.moving_since = t, None
            return
        if not any(speed_of(track) >= c.moving_speed for track in zone_tracks):
            self.moving_since = None
            return
        if self.moving_since is None:
            self.moving_since = t
        if t - self.moving_since >= c.moving_hold_sec:
            self.stationary_since = self.moving_since = None
            self.next_alarm_at = None

    def _stationary_sec(self, t):
        return 0.0 if self.stationary_since is None else t - self.stationary_since

    def _go(self, t, new_state, reason):
        self.transitions.append(Transition(t, self.state, new_state, reason))
        self.state, self.state_since = new_state, t
        self.clear_since = None
        self.tof_hold = False
        if new_state != WAITING:
            self.blocked_entry = False
        if new_state == DRIVING:
            # 기다리느라 서 있던 시간은 "막힘"이 아니다. 출발한 뒤 다시 2 s를 재야 한다. 안 그러면 대기가 끝나는 순간
            # 옆 1 m 안에 누가 서 있기만 해도 바로 blocked_in_zone으로 되돌아가 군중에서 대기가 꼬리를 물었다(10-20)
            self.stalled_since = None
        if new_state != WAITING:
            self.stationary_since = self.moving_since = None
            self.next_alarm_at = None

    def _status(self, t, reason, tracks=()):
        if self.state in (WAITING, PULL_OVER):
            count = len(self._zone_tracks(tracks))
        else:
            count = sum(1 for track in tracks if in_zone(track, self.config))
        return WaitStatus(
            state=self.state,
            wait=self.state in (WAITING, PULL_OVER),
            reason=reason,
            tracks_in_zone=count,
            elapsed_sec=t - self.state_since,
            stationary_sec=self._stationary_sec(t),
        )
