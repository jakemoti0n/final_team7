"""패드 기록 버튼(상승 에지 토글) 테스트. 앞쪽은 순수 판정, 마지막은 기록기 노드에서 바퀴 번호가 오르는지."""

import json
import os

from limbo_imitation import metrics, record_button, run_files
import pytest

START = 7
UP = [0] * 11
DOWN = [0] * 7 + [1] + [0] * 3


def edges(sequence, button=START):
    rb = record_button.RecordButton(button)
    return [rb.pressed_now(buttons) for buttons in sequence]


def test_held_button_toggles_once():
    assert edges([UP, DOWN, DOWN, DOWN, DOWN]) == [False, True, False, False, False]


def test_release_and_press_again_toggles_again():
    assert edges([DOWN, UP, DOWN, DOWN, UP, DOWN]) == [True, False, True, False, False, True]


def test_other_buttons_and_short_arrays_are_ignored():
    deadman_only = [0] * 4 + [1] + [0] * 6
    assert edges([deadman_only, [1, 1, 1], []]) == [False, False, False]


def test_toggle_action_alternates():
    assert record_button.toggle_action(False) == record_button.START
    assert record_button.toggle_action(True) == record_button.STOP


class PausedBag:
    """미리 띄운 bag 흉내(ros2 bag record를 띄우지 않으려고). SIGINT를 받으면 바로 끝난다."""

    pid = 12345

    def __init__(self, command):
        self.command = command
        self.code = None
        os.makedirs(command[command.index('-o') + 1])  # rosbag2처럼 bag 폴더를 만든다

    def poll(self):
        return self.code

    def send_signal(self, signum):
        self.code = 0

    def wait(self, timeout=None):
        return self.code


def test_button_start_stop_start_makes_numbered_runs(tmp_path, monkeypatch):
    rclpy = pytest.importorskip('rclpy')
    pytest.importorskip('limbo_interfaces.msg')
    from limbo_imitation import run_recorder
    from sensor_msgs.msg import Joy

    spawned = []
    monkeypatch.setattr(run_recorder.RunRecorder, 'spawn_bag',
                        lambda self, command: spawned.append(PausedBag(command)) or spawned[-1])
    rclpy.init(args=['--ros-args', '-p', f'output_root:={tmp_path}'])
    node = run_recorder.RunRecorder()
    try:
        assert node.log is None  # 버튼을 누르기 전에는 기록하지 않는다
        # 런치가 뜰 때 다음 바퀴용 bag을 일시 정지 상태로 미리 띄운다(임시 폴더, 노드 이름 구분)
        assert len(spawned) == 1 and '--start-paused' in spawned[0].command
        assert sorted(os.listdir(tmp_path)) == [run_files.standby_name(os.getpid(), 1)[0]]
        for buttons in [DOWN, DOWN, UP, DOWN, UP, DOWN]:  # 시작(누른 채 유지) → 끝 → 시작
            node.on_joy(Joy(buttons=buttons))
        assert node.run_number == 2 and node.log is not None
        # 바퀴마다 미리 띄운 것을 썼다: 런치 때 1 + 첫 바퀴 끝 1(둘째 바퀴가 쓴 것)
        assert len(spawned) == 2
        node.on_joy(Joy(buttons=UP))
        node.on_joy(Joy(buttons=DOWN))  # 둘째 바퀴 끝 → 다음 대기 bag
        assert node.log is None and len(spawned) == 3
        node.close_standby()  # 노드 종료 때: 쓰지 않은 대기 bag을 닫고 임시 폴더를 지운다
        assert spawned[2].code == 0
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    folders = sorted(os.listdir(tmp_path))
    assert [name.split('_')[2] for name in folders] == ['01', '02']
    names = [run_files.standby_name(os.getpid(), i)[1] for i in (1, 2, 3)]
    assert [bag.command[bag.command.index('--node-name') + 1] for bag in spawned] == names
    for name in folders:
        meta, rows = read_run(tmp_path / name)
        assert meta['start_reason'] == metrics.START_BUTTON
        assert meta['end_reason'] == metrics.START_BUTTON
        assert rows[0]['completed'] == metrics.COMPLETED_MANUAL
        expected = [run_files.BAG_DIR, run_files.META_FILE, run_files.METRICS_FILE,
                    run_files.TF_STATIC_FILE]
        assert sorted(os.listdir(tmp_path / name)) == expected


def read_run(folder):
    with open(folder / run_files.META_FILE, encoding='utf-8') as f:
        meta = json.load(f)
    return meta, run_files.read_metrics_csv(str(folder))
