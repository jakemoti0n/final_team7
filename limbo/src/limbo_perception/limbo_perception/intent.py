"""사람의 접근 의도(approach intent) 판단 (ROS 의존 없음)."""

from dataclasses import dataclass


@dataclass
class IntentConfig:
    # Interaction zone (base_link 기준, +Y 왼쪽 / -Y 오른쪽)
    interaction_min_x: float = 0.3
    interaction_max_x: float = 2.0
    interaction_half_width: float = 0.8
    # APPROACHING이 이 시간 이상 지속되어야 intent 확정
    approach_hold_time: float = 0.5
    # intent 확정 후 최소 유지시간
    intent_min_hold_time: float = 2.0
    # 잠깐 detection이 끊겨도 intent 유지
    intent_lost_grace_time: float = 1.0


def update_approach_intent(track, motion_state, person_base_x, person_base_y,
                           current_time, config):
    """track의 intent 상태를 갱신하고 (intent 여부, 지속 시간)을 반환한다."""
    if track is None:
        return False, 0.0

    in_zone = (
        config.interaction_min_x <= person_base_x <= config.interaction_max_x
        and abs(person_base_y) <= config.interaction_half_width
    )

    if track.intent_confirmed:
        confirmed_duration = current_time - track.intent_confirmed_time

        # 로봇 앞에서 멈춰 서도 여전히 다가온 사람이므로 intent를 유지한다
        if in_zone:
            return True, confirmed_duration

        # zone 경계에서 깜빡이지 않도록 최소 시간은 유지한다
        if confirmed_duration < config.intent_min_hold_time:
            return True, confirmed_duration

        track.intent_confirmed = False
        track.intent_confirmed_time = None
        track.approach_start_time = None
        return False, 0.0

    candidate = motion_state == 'APPROACHING' and in_zone

    if not candidate:
        track.approach_start_time = None
        return False, 0.0

    if track.approach_start_time is None:
        track.approach_start_time = current_time
        return False, 0.0

    duration = current_time - track.approach_start_time

    if duration >= config.approach_hold_time:
        track.intent_confirmed = True
        track.intent_confirmed_time = current_time
        return True, duration

    return False, duration


def any_recent_confirmed_intent(tracks, current_time, config):
    """확정된 intent 중 최근 grace time 안에 보인 사람이 있는지 확인한다."""
    for track in tracks:
        if not track.intent_confirmed:
            continue
        # 잠깐 검출이 끊겨도 intent가 꺼지지 않게 한다
        if current_time - track.last_seen <= config.intent_lost_grace_time:
            return True
    return False
