"""주행 중재기 판단 단위 테스트."""

from limbo_imitation import arbiter_logic as al
import pytest

S = al.Settings(command_timeout=0.5, stuck_speed=0.05, stuck_timeout=3.0)


def inputs(now=10.0, mode='policy', **overrides):
    """모든 입력이 방금 들어온 상태. 정책 0.4 m/s, nav 0.3, teleop 0.2, 정책 상태 ok."""
    base = {'now': now, 'mode': mode,
            'teleop': (0.2, 0.1), 'teleop_time': now, 'policy': (0.4, 0.0), 'policy_time': now,
            'nav': (0.3, -0.1), 'nav_time': now, 'deadman': False, 'joy_time': now,
            'status_ok': True, 'status_reason': '', 'status_time': now,
            'odom_speed': 0.4, 'odom_time': now}
    base.update(overrides)
    return al.Inputs(**base)


def settle(state, given):
    """첫 틱은 전환 평균이 들어가므로 한 번 더 돌려 안정된 출력을 본다."""
    al.step(state, given, S)
    return al.step(state, given, S)


@pytest.mark.parametrize('mode', al.MODES)
def test_deadman_wins_in_every_mode(mode):
    output, source, _ = settle(al.State(), inputs(mode=mode, deadman=True))
    assert source == 'teleop' and output == (0.2, 0.1)


def test_stale_joy_is_not_deadman():
    _, source, _ = settle(al.State(), inputs(mode='manual', deadman=True, joy_time=9.0))
    assert source == 'none'


def test_manual_without_deadman_outputs_zero():
    output, source, _ = settle(al.State(), inputs(mode='manual'))
    assert source == 'none' and output == (0.0, 0.0)


def test_keyboard_manual_without_deadman_passes_fresh_teleop():
    keyboard = al.Settings(require_deadman=False)
    state = al.State()
    given = inputs(mode='manual', joy_time=None)
    al.step(state, given, keyboard)
    output, source, _ = al.step(state, given, keyboard)
    assert source == 'teleop' and output == (0.2, 0.1)


def test_keyboard_manual_stops_when_keys_released():
    keyboard = al.Settings(require_deadman=False)
    state = al.State()
    given = inputs(mode='manual', joy_time=None, teleop_time=9.0)
    al.step(state, given, keyboard)
    output, source, _ = al.step(state, given, keyboard)
    assert source == 'none' and output == (0.0, 0.0)


def test_require_deadman_false_does_not_affect_policy_mode():
    _, source, _ = settle(al.State(), inputs(mode='policy'))
    keyboard = al.Settings(require_deadman=False)
    state = al.State()
    al.step(state, inputs(mode='policy'), keyboard)
    assert al.step(state, inputs(mode='policy'), keyboard)[1] == source == 'policy'


def test_nav_mode_passes_nav_command():
    output, source, _ = settle(al.State(), inputs(mode='nav'))
    assert source == 'nav' and output == (0.3, -0.1)


def test_policy_mode_uses_policy():
    output, source, _ = settle(al.State(), inputs(mode='policy_assist'))
    assert source == 'policy' and output == (0.4, 0.0)


def test_status_not_ok_falls_back_to_nav_and_returns_on_new_ok():
    state = al.State()
    settle(state, inputs(status_ok=False, status_reason='unseen corridor'))
    assert state.source == 'nav' and 'unseen corridor' in state.fallback
    # 넘긴 뒤 새 status가 아직 안 옴 → nav 유지
    _, source, _ = al.step(state, inputs(now=10.1, status_time=10.0), S)
    assert source == 'nav'
    _, source, _ = al.step(state, inputs(now=10.2), S)
    assert source == 'policy'


def test_policy_command_lost_falls_back_to_nav():
    _, source, reason = settle(al.State(), inputs(policy_time=9.0))
    assert source == 'nav' and reason == 'policy command lost'


def test_no_status_ever_falls_back_to_nav():
    _, source, _ = settle(al.State(), inputs(status_time=None))
    assert source == 'nav'


def test_stuck_falls_back_and_returns_only_after_moving_again():
    state = al.State()
    for k in range(31):  # 0.1 s마다 3.0 s 동안 정책은 밀고 로봇은 안 움직임
        t = 10.0 + k * 0.1
        _, source, reason = al.step(state, inputs(now=t, odom_speed=0.0), S)
    assert source == 'nav' and reason == 'stuck'
    _, source, _ = al.step(state, inputs(now=13.2, odom_speed=0.0), S)
    assert source == 'nav'  # status는 ok지만 아직 안 움직임
    _, source, _ = al.step(state, inputs(now=13.3, odom_speed=0.2), S)
    assert source == 'policy'


def test_deadman_overrides_fallback_and_release_keeps_fallback():
    state = al.State()
    settle(state, inputs(status_ok=False))
    _, source, _ = al.step(state, inputs(now=10.1, status_ok=False, deadman=True), S)
    assert source == 'teleop'
    _, source, _ = al.step(state, inputs(now=10.2, status_ok=False), S)
    assert source == 'nav'


def test_reverse_is_zeroed_from_any_source():
    for mode, field in (('nav', 'nav'), ('policy', 'policy')):
        output, _, _ = settle(al.State(), inputs(mode=mode, **{field: (-0.3, 0.5)}))
        assert output == (0.0, 0.5)
    output, _, _ = settle(al.State(), inputs(mode='manual', deadman=True, teleop=(-0.2, 0.0)))
    assert output == (0.0, 0.0)


def test_lost_selected_command_outputs_zero():
    output, source, reason = settle(al.State(), inputs(mode='nav', nav_time=9.0))
    assert output == (0.0, 0.0) and source == 'none' and reason == 'nav command lost'


def test_switch_tick_averages_previous_output_and_new_command():
    state = al.State()
    settle(state, inputs(mode='nav'))  # 출력 (0.3, -0.1)
    output, source, _ = al.step(state, inputs(mode='nav', deadman=True), S)
    assert source == 'teleop' and output == pytest.approx((0.25, 0.0))
    output, _, _ = al.step(state, inputs(mode='nav', deadman=True), S)
    assert output == (0.2, 0.1)


def test_parse_policy_status():
    assert al.parse_policy_status('{"ok": true, "reason": ""}') == (True, '')
    assert al.parse_policy_status('{"ok": false, "reason": "far"}') == (False, 'far')
    assert al.parse_policy_status('not json')[0] is False
    assert al.parse_policy_status('{"reason": "x"}')[0] is False
