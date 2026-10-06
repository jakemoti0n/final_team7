"""Adapter extraction test; real DDS tests are in tools/validate_ros.py."""
from types import SimpleNamespace
import weakref
import pytest
pytest.importorskip('rclpy')
from limbo_telemetry_bridge.node import BridgeNode
from limbo_telemetry_bridge.state import State, TOPICS


class Message:
    def __init__(self):
        self.header = SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
        self.twist = SimpleNamespace(twist=SimpleNamespace(
            linear=SimpleNamespace(x=3., y=4.), angular=SimpleNamespace(z=-1.)))

    @property
    def data(self):
        raise AssertionError('raw buffer must never be accessed')


def test_callback_does_not_access_or_retain_raw_message():
    owner = SimpleNamespace(state=State())
    for key in TOPICS:
        callback = BridgeNode._callback(owner, key)
        message = Message()
        ref = weakref.ref(message)
        callback(message)
        del message
        assert ref() is None
    snapshot = owner.state.snapshot()
    assert snapshot['motion']['linear_speed_mps'] == 5
    assert all(t['header_stamp'] == {'sec':0, 'nanosec':0} for t in snapshot['topics'].values())
