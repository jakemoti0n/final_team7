"""Shutdown races may be ignored only after the ROS context is closed."""
from unittest.mock import Mock
import pytest
from limbo_perception import person_wait_node as module


@pytest.mark.parametrize('active,message,raises', [
    (False, "Unable to convert call argument '0' to Python object", False),
    (True, "Unable to convert call argument '0' to Python object", True),
    (False, 'unexpected operational failure', True),
])
def test_only_known_post_shutdown_conversion_error_is_tolerated(monkeypatch,active,message,raises):
    node=Mock()
    monkeypatch.setattr(module,'PersonWaitNode',lambda:node)
    monkeypatch.setattr(module.rclpy,'init',Mock())
    monkeypatch.setattr(module.rclpy,'ok',lambda:active)
    monkeypatch.setattr(module.rclpy,'try_shutdown',Mock())
    monkeypatch.setattr(module.rclpy,'spin',Mock(side_effect=RuntimeError(message)))
    if raises:
        with pytest.raises(RuntimeError,match=message):module.main()
    else:
        module.main()
    node.destroy_node.assert_called_once()
    module.rclpy.try_shutdown.assert_called_once()
