"""
바퀴 기록 버튼 판정: 패드 버튼을 누른 순간(상승 에지)에만 기록 시작/끝을 한 번 토글한다. rclpy를 쓰지 않는다.

런치는 하루 한 번 띄워 두고 바퀴마다 버튼으로 기록을 시작하고 끝낸다(2026-11-26 B안).
패드 켜기(joy·teleop·중재기)와 기록이 한 런치에 묶여 있어 바퀴마다 런치를 껐다 켜야 했고
바퀴 사이 이동·연습까지 기록되던 문제 때문이다.
joy_node는 버튼을 누르고 있는 동안 같은 값(1)을 계속 보내므로, 값이 아니라 0 → 1로 바뀐 순간만 센다.
"""

START = 'start'
STOP = 'stop'


class RecordButton:
    """버튼 하나의 이전 값을 기억해 상승 에지를 찾는다."""

    def __init__(self, button):
        self.button = button
        self.was_pressed = False

    def is_pressed(self, buttons):
        """buttons는 sensor_msgs/Joy.buttons. 버튼 번호가 배열 밖이면(다른 패드 배열) 안 눌린 것으로 본다."""
        return 0 <= self.button < len(buttons) and buttons[self.button] == 1

    def pressed_now(self, buttons):
        """이번 메시지에서 막 눌렸으면 True. 누르고 있는 동안은 처음 한 번만 True."""
        pressed = self.is_pressed(buttons)
        edge = pressed and not self.was_pressed
        self.was_pressed = pressed
        return edge


def toggle_action(recording):
    """버튼을 눌렀을 때 할 일. 기록 중이면 끝, 아니면 새 바퀴 시작."""
    return STOP if recording else START
