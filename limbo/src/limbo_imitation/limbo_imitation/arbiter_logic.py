"""
주행 중재기(drive_arbiter)의 판단. rclpy를 쓰지 않는다.

세 명령(조이스틱 teleop, 정책, MPPI nav) 중 바퀴로 보낼 하나를 고른다. 우선순위:
1. 데드맨 버튼이 눌려 있으면 어느 모드든 teleop. 사람이 잡으면 사람이 이긴다.
2. manual: teleop만(데드맨 없으면 정지. require_deadman=false면 teleop 명령이 신선한 동안 통과).
3. nav: MPPI 명령 그대로(중재기 넣기 전과 같은 동작).
4. policy·policy_assist: 정책 명령. 정책이 학습 범위 밖이라고 하거나(status ok=false),
   정책 명령이 끊기거나, 갇히면 nav로 넘긴다. 넘긴 뒤 복귀 조건은 policy_ready 참고.
고른 명령이 command_timeout보다 오래됐으면 0을 낸다.
"""

from dataclasses import dataclass
import json

MODES = ('manual', 'policy_assist', 'policy', 'nav')
POLICY_MODES = ('policy', 'policy_assist')
ZERO = (0.0, 0.0)


@dataclass
class Settings:
    command_timeout: float = 0.5
    stuck_speed: float = 0.05
    stuck_timeout: float = 3.0
    require_deadman: bool = True


@dataclass
class Inputs:
    """노드가 구독한 최신 값과 받은 시각(초). 한 번도 안 왔으면 시각은 None."""

    now: float = 0.0
    mode: str = 'nav'
    teleop: tuple = ZERO
    teleop_time: float = None
    policy: tuple = ZERO
    policy_time: float = None
    nav: tuple = ZERO
    nav_time: float = None
    deadman: bool = False
    joy_time: float = None
    status_ok: bool = False
    status_reason: str = 'no status yet'
    status_time: float = None
    odom_speed: float = 0.0
    odom_time: float = None


@dataclass
class State:
    """틱 사이에 이어지는 것: 직전 출처·출력, 갇힘 시작 시각, nav로 넘긴 이유."""

    source: str = 'none'
    output: tuple = ZERO
    stuck_since: float = None
    fallback: str = None
    fallback_time: float = None


def parse_policy_status(text):
    """/policy/status 문자열(JSON {"ok": bool, "reason": str}) → (ok, reason).

    정책 노드가 아직 없어 형식을 가정했다. 형식이 바뀌면 이 함수만 고친다.
    읽을 수 없는 메시지는 학습 범위 밖과 같이 취급한다(모르면 nav가 안전하다).
    """
    try:
        data = json.loads(text)
        return bool(data['ok']), str(data.get('reason', ''))
    except (ValueError, KeyError, TypeError):
        return False, 'unreadable status'


def is_fresh(stamp, now, timeout):
    return stamp is not None and now - stamp <= timeout


def no_reverse(command):
    """후진 명령은 0으로. 뒤를 보는 센서가 없어서다(설계 2-3). 회전은 그대로 둔다."""
    return (max(command[0], 0.0), command[1])


def deadman_held(inputs, settings):
    """/joy가 끊겼으면 눌림으로 보지 않는다. 마지막 '눌림'이 남아 계속 teleop이 되지 않게."""
    return inputs.deadman and is_fresh(inputs.joy_time, inputs.now, settings.command_timeout)


def update_stuck(state, inputs, settings):
    """정책이 가라는데(v > stuck_speed) 로봇이 안 움직이는 상태가 stuck_timeout 이어지면 참."""
    odom_ok = is_fresh(inputs.odom_time, inputs.now, settings.command_timeout)
    pushing = inputs.policy[0] > settings.stuck_speed
    if not (odom_ok and pushing and abs(inputs.odom_speed) < settings.stuck_speed):
        state.stuck_since = None
        return False
    if state.stuck_since is None:
        state.stuck_since = inputs.now
    return inputs.now - state.stuck_since >= settings.stuck_timeout


def policy_problem(state, inputs, settings):
    """정책 명령을 쓰면 안 되는 이유. 없으면 None."""
    if inputs.status_time is None:
        return 'no policy status'
    if not inputs.status_ok:
        return 'policy out of range: ' + inputs.status_reason
    if not is_fresh(inputs.policy_time, inputs.now, settings.command_timeout):
        return 'policy command lost'
    if update_stuck(state, inputs, settings):
        return 'stuck'
    return None


def policy_ready(state, inputs, settings):
    """nav로 넘긴 뒤 정책으로 돌아가도 되는가.

    status가 넘긴 뒤에 새로 ok=true로 와야 한다(넘기기 전 마지막 ok를 다시 믿지 않게).
    갇힘으로 넘긴 경우는 nav가 로봇을 다시 움직이게 한 뒤에만 돌아간다. 아니면 정책이
    같은 자리에서 다시 밀다가 stuck_timeout마다 nav와 정책을 오가기 때문이다.
    """
    fresh_ok = (inputs.status_ok and inputs.status_time is not None
                and inputs.status_time > state.fallback_time)
    command_ok = is_fresh(inputs.policy_time, inputs.now, settings.command_timeout)
    if state.fallback == 'stuck':
        moving = abs(inputs.odom_speed) >= settings.stuck_speed
        return fresh_ok and command_ok and moving
    return fresh_ok and command_ok


def choose_policy_or_nav(state, inputs, settings):
    """정책 모드들(policy·policy_assist)의 출처: ('policy' 또는 'nav', 이유)."""
    if state.fallback is not None:
        if not policy_ready(state, inputs, settings):
            return 'nav', state.fallback
        state.fallback = None
        state.stuck_since = None
    problem = policy_problem(state, inputs, settings)
    if problem is not None:
        state.fallback, state.fallback_time = problem, inputs.now
        state.stuck_since = None
        return 'nav', problem
    return 'policy', 'policy ok'


def choose_manual(inputs, settings):
    """수동(manual) 모드에서 데드맨이 안 눌렸을 때.

    require_deadman=false는 조이스틱이 없을 때 키보드로 운전하기 위한 대안이다(키보드엔 데드맨이 없다).
    키를 떼면 teleop 명령이 끊겨 command_timeout 뒤 멈추고, 안전 정지는 collision_monitor가 그대로 맡는다.
    """
    if not settings.require_deadman and is_fresh(inputs.teleop_time, inputs.now,
                                                 settings.command_timeout):
        return 'teleop', 'teleop without deadman'
    return 'none', 'manual without deadman'


def choose_source(state, inputs, settings):
    """(출처, 이유). 출처는 teleop·policy·nav·none."""
    if deadman_held(inputs, settings):
        return 'teleop', 'deadman held'
    if inputs.mode == 'manual':
        return choose_manual(inputs, settings)
    if inputs.mode == 'nav':
        return 'nav', 'nav mode'
    if inputs.mode in POLICY_MODES:
        return choose_policy_or_nav(state, inputs, settings)
    return 'none', 'unknown mode ' + inputs.mode


def source_command(source, inputs, settings):
    """출처의 명령. 출처가 없거나 명령이 끊겼으면 (0, 0)과 끊김 여부."""
    commands = {
        'teleop': (inputs.teleop, inputs.teleop_time),
        'policy': (inputs.policy, inputs.policy_time),
        'nav': (inputs.nav, inputs.nav_time),
    }
    if source not in commands:
        return ZERO, False
    command, stamp = commands[source]
    if not is_fresh(stamp, inputs.now, settings.command_timeout):
        return ZERO, True
    return no_reverse(command), False


def step(state, inputs, settings):
    """한 틱: (출력 (v, w), 출처, 이유). state를 갱신한다.

    출처가 바뀌는 틱에만 이전 출력과 새 명령을 평균한다. 출처마다 속도가 크게 다를 수 있어
    한 틱에 바로 바꾸면 바퀴가 덜컥인다. 가속 제한 자체는 정책 노드·velocity_smoother 몫이라
    여기서는 전환 순간의 계단 하나만 줄인다.
    """
    source, reason = choose_source(state, inputs, settings)
    command, lost = source_command(source, inputs, settings)
    if lost:
        reason = source + ' command lost'
        source = 'none'
    if source != state.source:
        command = ((state.output[0] + command[0]) / 2.0, (state.output[1] + command[1]) / 2.0)
    state.source, state.output = source, command
    return command, source, reason
