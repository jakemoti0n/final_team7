"""사람 track 관리: BoT-SORT ID 재연결 + 사람별 칼만 필터 (ROS 의존 없음)."""

from dataclasses import dataclass
import math
from typing import Optional

from limbo_perception.kalman import PersonKalmanFilter
import numpy as np

# dt가 이 범위를 벗어나면 예측이 무의미해서 칼만 필터를 재시작한다
MIN_VALID_DT = 0.001
MAX_VALID_DT = 3.0


@dataclass
class TrackerConfig:
    # ID가 바뀌었을 때 기존 track과 재연결을 시도할 최대 시간 (sec)
    reassociate_max_age: float = 3.0
    # Kalman 예상 위치와 새 detection 위치의 최대 허용 거리 (m)
    reassociate_max_distance: float = 0.50
    # ID switch / 이상치 방어 (m)
    max_position_jump: float = 0.8
    # 최소 몇 frame 살아남아야 신뢰할지
    min_track_hits: int = 5
    # 이 시간 이상 안 보이면 track 제거 (sec)
    track_timeout: float = 3.0
    kalman_measurement_noise: float = 0.05
    kalman_process_noise: float = 0.5


@dataclass
class Track:
    kalman: PersonKalmanFilter
    last_time: float
    last_seen: float
    hits: int = 1
    # intent.py가 갱신한다
    approach_start_time: Optional[float] = None
    intent_confirmed: bool = False
    intent_confirmed_time: Optional[float] = None
    # BoT-SORT ID가 바뀌었을 때 같은 사람인지 판단하려고 남겨 둔다 (odom 기준)
    manager_x: Optional[float] = None
    manager_y: Optional[float] = None
    manager_vx: float = 0.0
    manager_vy: float = 0.0
    manager_last_seen: Optional[float] = None

    def predicted_position(self, current_time):
        """마지막 필터 결과를 등속으로 외삽한 위치와 경과 시간을 반환한다."""
        age = current_time - self.manager_last_seen
        return (
            self.manager_x + self.manager_vx * age,
            self.manager_y + self.manager_vy * age,
            age,
        )


@dataclass
class TrackObservation:
    person_id: int
    x: float
    y: float
    vx: float
    vy: float
    stable: bool


class TrackManager:
    """BoT-SORT raw ID를 Limbo person ID로 바꾸고 사람별 칼만 필터를 관리한다."""

    def __init__(self, config, logger=None):
        self.config = config
        self.logger = logger
        self.tracks = {}
        self.raw_to_person_id = {}
        self.person_to_raw_id = {}
        # BoT-SORT ID는 사람이 가려지면 바뀌므로 Limbo가 따로 ID를 발급한다
        self.next_person_id = 1

    def observe(self, raw_track_id, measured_x, measured_y, current_time,
                matched_person_ids):
        """검출 하나를 person에 연결하고 필터를 갱신한다."""
        person_id = self.resolve_person_id(
            raw_track_id, measured_x, measured_y, current_time,
            matched_person_ids)
        matched_person_ids.add(person_id)

        x, y, vx, vy, stable = self.update_track(
            person_id, measured_x, measured_y, current_time)

        track = self.tracks[person_id]
        track.manager_x = x
        track.manager_y = y
        track.manager_vx = vx
        track.manager_vy = vy
        track.manager_last_seen = current_time

        return TrackObservation(person_id, x, y, vx, vy, stable)

    def _new_kalman(self, x, y):
        return PersonKalmanFilter(
            x, y,
            measurement_noise=self.config.kalman_measurement_noise,
            process_noise=self.config.kalman_process_noise)

    def _restart(self, track, measured_x, measured_y, current_time):
        # 이상한 측정으로 기존 필터를 망가뜨리지 않으려고 새 track처럼 시작한다
        track.kalman = self._new_kalman(measured_x, measured_y)
        track.last_time = current_time
        track.last_seen = current_time
        track.hits = 1
        track.approach_start_time = None
        return measured_x, measured_y, 0.0, 0.0, False

    def update_track(self, track_id, measured_x, measured_y, current_time):
        """(x, y, vx, vy, stable)을 반환한다."""
        if track_id not in self.tracks:
            self.tracks[track_id] = Track(
                kalman=self._new_kalman(measured_x, measured_y),
                last_time=current_time,
                last_seen=current_time,
            )
            return measured_x, measured_y, 0.0, 0.0, False

        track = self.tracks[track_id]
        dt = current_time - track.last_time

        if dt <= MIN_VALID_DT or dt > MAX_VALID_DT:
            self._warn(f'KF RESET TIME: ID={track_id}, dt={dt:.3f}')
            return self._restart(track, measured_x, measured_y, current_time)

        track.kalman.predict(dt)
        predicted_x, predicted_y, _, _ = track.kalman.get_state()

        jump = np.sqrt(
            (measured_x - predicted_x) ** 2 + (measured_y - predicted_y) ** 2)
        if jump > self.config.max_position_jump:
            self._warn(f'Possible ID switch: ID={track_id}, jump={jump:.2f}m')
            self._warn(f'KF RESET JUMP: ID={track_id}, jump={jump:.2f}')
            return self._restart(track, measured_x, measured_y, current_time)

        track.kalman.update(measured_x, measured_y)
        x, y, vx, vy = track.kalman.get_state()

        track.last_time = current_time
        track.last_seen = current_time
        track.hits += 1

        # 막 생긴 track은 속도 추정이 불안정해서 몇 frame 지난 뒤부터 쓴다
        stable = track.hits >= self.config.min_track_hits
        return x, y, vx, vy, stable

    def _reassociation_distance(self, track, measured_x, measured_y,
                                current_time):
        """재연결 가능한 track이면 예상 위치까지 거리, 아니면 None."""
        if track.manager_x is None or track.manager_last_seen is None:
            return None

        predicted_x, predicted_y, age = track.predicted_position(current_time)

        if age < 0.0 or age > self.config.reassociate_max_age:
            return None

        return math.hypot(measured_x - predicted_x, measured_y - predicted_y)

    def resolve_person_id(self, raw_track_id, measured_x, measured_y,
                          current_time, matched_person_ids):
        """
        BoT-SORT raw ID를 Limbo 내부 person ID로 변환한다.

        1. 기존 raw ID가 정상적으로 이어지고 있으면 그대로 사용
        2. raw ID가 바뀌었으면 Kalman 예상 위치와 비교해서 기존 person과 재연결
        3. 연결할 사람이 없으면 새로운 person ID 생성
        """
        raw_track_id = int(raw_track_id)
        max_distance = self.config.reassociate_max_distance

        if raw_track_id in self.raw_to_person_id:
            person_id = self.raw_to_person_id[raw_track_id]
            if (person_id in self.tracks
                    and person_id not in matched_person_ids):
                distance = self._reassociation_distance(
                    self.tracks[person_id], measured_x, measured_y,
                    current_time)
                if distance is not None and distance <= max_distance:
                    return person_id

        best_person_id = None
        best_distance = float('inf')

        for person_id, track in self.tracks.items():
            # 한 사람에게 두 detection이 붙지 않게 한다
            if person_id in matched_person_ids:
                continue

            distance = self._reassociation_distance(
                track, measured_x, measured_y, current_time)
            if distance is None:
                continue

            if distance <= max_distance and distance < best_distance:
                best_distance = distance
                best_person_id = person_id

        if best_person_id is not None:
            old_raw_id = self.person_to_raw_id.get(best_person_id)

            if (old_raw_id is not None
                    and self.raw_to_person_id.get(old_raw_id) == best_person_id):
                del self.raw_to_person_id[old_raw_id]

            self.raw_to_person_id[raw_track_id] = best_person_id
            self.person_to_raw_id[best_person_id] = raw_track_id

            if old_raw_id != raw_track_id:
                self._info(
                    f'[TRACK MANAGER] BoT-SORT ID {old_raw_id} -> '
                    f'{raw_track_id}, keep person_id={best_person_id}, '
                    f'distance={best_distance:.2f}m')

            return best_person_id

        new_person_id = self.next_person_id
        self.next_person_id += 1

        self.raw_to_person_id[raw_track_id] = new_person_id
        self.person_to_raw_id[new_person_id] = raw_track_id

        self._info(
            f'[TRACK MANAGER] New person_id={new_person_id}, '
            f'raw_track_id={raw_track_id}')

        return new_person_id

    def cleanup(self, current_time):
        """timeout된 track과 그 ID mapping을 함께 삭제한다."""
        remove_ids = [
            person_id for person_id, track in self.tracks.items()
            if current_time - track.last_seen > self.config.track_timeout
        ]

        for person_id in remove_ids:
            raw_track_id = self.person_to_raw_id.pop(person_id, None)

            if (raw_track_id is not None
                    and self.raw_to_person_id.get(raw_track_id) == person_id):
                del self.raw_to_person_id[raw_track_id]

            # 재연결 과정에서 같은 person을 가리키는 raw ID가 남을 수 있다
            stale_raw_ids = [
                raw_id for raw_id, mapped in self.raw_to_person_id.items()
                if mapped == person_id
            ]
            for raw_id in stale_raw_ids:
                del self.raw_to_person_id[raw_id]

            del self.tracks[person_id]

    def _warn(self, text):
        if self.logger is not None:
            self.logger.warn(text)

    def _info(self, text):
        if self.logger is not None:
            self.logger.info(text)
