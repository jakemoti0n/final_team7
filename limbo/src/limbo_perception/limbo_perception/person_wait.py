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
    release_sec: float = 0.5        # s, 구역이 빈 채 이만큼 지나면 출발. 긴 끊김은 트랙 grace 몫이라 짧게
    service_sec: float = 15.0       # s, T_service. 쓰레기를 버리는 데 드는 시간(2-7 결정 10-19)
    alarm_period_sec: float = 30.0  # s, 비켜설 자리 없이 계속 기다릴 때 경보 간격(2-7)

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
        self.next_alarm_at = None
        self.transitions = []          # Transition 목록. 노드가 새로 생긴 것만 로그로 찍는다

    def on_tick(self, t, tracks, ready, pull_over_available=False, pull_over_done=False):
        """tracks: base_link 기준 (rel_x, rel_y, vx, vy) 목록(속도도 base_link 축, m/s)."""
        if self.state_since is None:
            self.state_since = t
        if not ready:
            if self.state != NOT_READY:
                self._go(t, NOT_READY, 'not_ready')
            return self._status(t, 'not_ready')
        if self.state == NOT_READY:
            self._go(t, DRIVING, 'ready')
            return self._status(t, 'ready')
        if self.state == DRIVING:
            return self._tick_driving(t, tracks)
        if self.state == WAITING:
            return self._tick_waiting(t, tracks, pull_over_available)
        return self._tick_pull_over(t, tracks, pull_over_done)

    def _tick_driving(self, t, tracks):
        c = self.config
        if any(is_approaching(track, c) for track in tracks):
            self._go(t, WAITING, 'approaching')
            return self._status(t, 'approaching', tracks)
        if any(in_zone(track, c) for track in tracks):
            self._go(t, WAITING, 'in_zone')
            self._update_stationary(t, self._zone_tracks(tracks))   # 서비스 시간은 선 순간부터 잰다
            return self._status(t, 'in_zone', tracks)
        return self._status(t, 'clear', tracks)

    def _tick_waiting(self, t, tracks, pull_over_available):
        c = self.config
        zone_tracks = self._zone_tracks(tracks)
        approaching = any(is_approaching(track, c) for track in tracks)
        if zone_tracks or approaching:
            self.clear_since = None
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

    def _zone_tracks(self, tracks):
        """기다리는 중에는 넓힌 구역으로 본다(들어올 때보다 나갈 때 경계가 멀어야 안 떤다)."""
        return [track for track in tracks
                if in_zone(track, self.config, self.config.zone_exit_margin)]

    def _update_stationary(self, t, zone_tracks):
        all_still = bool(zone_tracks) and all(
            speed_of(track) < self.config.min_speed for track in zone_tracks)
        if not all_still:
            self.stationary_since = None
            self.next_alarm_at = None
        elif self.stationary_since is None:
            self.stationary_since = t

    def _stationary_sec(self, t):
        return 0.0 if self.stationary_since is None else t - self.stationary_since

    def _go(self, t, new_state, reason):
        self.transitions.append(Transition(t, self.state, new_state, reason))
        self.state, self.state_since = new_state, t
        self.clear_since = None
        if new_state != WAITING:
            self.stationary_since = None
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
