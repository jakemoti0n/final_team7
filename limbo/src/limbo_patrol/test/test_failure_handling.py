"""이동 실패 처리: 다시 보내기, 끝내지 않고 멈춰 기다리기, 지난 지점으로 안 돌아가기 (CONTROL_SCREEN.md A 4단계)."""
import threading
import time
from types import SimpleNamespace

from limbo_interfaces.msg import PatrolState
from limbo_patrol import patrol_node
from nav2_simple_commander.robot_navigator import TaskResult
import pytest
import rclpy
from std_srvs.srv import Trigger

WAYPOINTS = [
    {'name': 'A', 'type': 'pass', 'x': 1.0, 'y': 0.0, 'yaw': 0.0, 'wait_sec': 0},
    {'name': 'B', 'type': 'pass', 'x': 2.0, 'y': 0.0, 'yaw': 0.0, 'wait_sec': 0},
    {'name': 'C', 'type': 'stop', 'x': 3.0, 'y': 0.0, 'yaw': 0.0, 'wait_sec': 0},
]


class FakeNavigator:
    """정해 둔 순서로 (결과, 실패 때 남은 지점 수)를 돌려준다."""

    def __init__(self, results):
        self.results = list(results)
        self.routes = []
        self.clock = rclpy.clock.Clock()
        self.current = None

    def get_clock(self):
        return self.clock

    def waitUntilNav2Active(self, localizer=None):
        pass

    def goThroughPoses(self, route):
        self.routes.append([p.pose.position.x for p in route])
        self.current = self.results.pop(0)
        self.polled = False
        return True

    def isTaskComplete(self):
        # 한 번은 주행 중으로 답해 순찰 노드가 진행 정보(남은 지점 수)를 읽게 한다
        done, self.polled = self.polled, True
        return done

    def getFeedback(self):
        left = self.current[1]
        return None if left is None else SimpleNamespace(number_of_poses_remaining=left)

    def getResult(self):
        return self.current[0]

    def cancelTask(self):
        pass


@pytest.fixture
def control(monkeypatch):
    rclpy.init()
    monkeypatch.setattr(patrol_node, 'wait_for_localization', lambda navigator: None)
    node = patrol_node.PatrolControl([w['name'] for w in WAYPOINTS])
    yield node
    node.destroy_node()
    rclpy.shutdown()


def run(navigator, control):
    thread = threading.Thread(
        target=patrol_node.patrol, args=(navigator, control, WAYPOINTS),
        kwargs={'retries': 2, 'retry_delay_sec': 0.05}, daemon=True)
    thread.start()
    return thread


def wait_state(control, state, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if control.state == state:
            return
        time.sleep(0.01)
    raise AssertionError(f'state {control.state}, expected {state}')


def test_one_failure_is_retried_and_patrol_goes_on(control):
    navigator = FakeNavigator([(TaskResult.FAILED, None), (TaskResult.SUCCEEDED, None)])
    run(navigator, control).join(5)
    assert control.state == PatrolState.COMPLETED
    assert len(navigator.routes) == 2


def test_retries_exhausted_pauses_instead_of_ending_and_resume_continues(control):
    navigator = FakeNavigator([(TaskResult.FAILED, None)] * 3 + [(TaskResult.SUCCEEDED, None)])
    thread = run(navigator, control)
    wait_state(control, PatrolState.PAUSED)
    assert len(navigator.routes) == 3          # 처음 + 다시 2번
    assert control.resumable                   # 재개 버튼이 열려 있어야 한다
    response = control.on_resume(Trigger.Request(), Trigger.Response())
    assert response.success
    thread.join(5)
    assert control.state == PatrolState.COMPLETED
    assert len(navigator.routes) == 4


def test_retry_does_not_go_back_to_passed_waypoints(control):
    # 첫 시도에서 A를 지나 B·C가 남은 채 실패
    navigator = FakeNavigator([(TaskResult.FAILED, 2), (TaskResult.SUCCEEDED, None)])
    run(navigator, control).join(5)
    assert navigator.routes == [[1.0, 2.0, 3.0], [2.0, 3.0]]


def test_pause_during_retry_wait_pauses_by_request(control):
    navigator = FakeNavigator([(TaskResult.FAILED, None), (TaskResult.SUCCEEDED, None)])
    with control.lock:
        control.pause_requested = True   # 다시 보내기 전 대기 중에 들어온 정지 요청
    thread = run(navigator, control)
    wait_state(control, PatrolState.PAUSED)
    control.on_resume(Trigger.Request(), Trigger.Response())
    thread.join(5)
    assert control.state == PatrolState.COMPLETED
