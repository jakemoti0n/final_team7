"""Launch parameter wiring tests; Node actions are mocked, no processes start."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml
from launch import LaunchContext


class LaunchTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'launch/encoders_odometry.launch.py'
        spec = importlib.util.spec_from_file_location('odom_launch_under_test', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.encoder_file = Path(self.temp.name)/'encoder.yaml'
        self.odom_file = Path(self.temp.name)/'odom.yaml'
        self.encoder = {'roboclaw_encoder': {'ros__parameters': {
            'left_counts_per_revolution': 4000.0, 'right_counts_per_revolution': 3000.0}}}
        self.odom = {'wheel_odometry': {'ros__parameters': {
            'left_wheel_radius': .075, 'right_wheel_radius': .075, 'wheel_separation': .54}}}
        self.context = LaunchContext()
        self.context.launch_configurations['publish_tf'] = 'false'
        self.context.launch_configurations['encoder_params_file'] = str(self.encoder_file)
        self.context.launch_configurations['odom_params_file'] = str(self.odom_file)

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        self.encoder_file.write_text(yaml.safe_dump(self.encoder), encoding='utf-8')
        self.odom_file.write_text(yaml.safe_dump(self.odom), encoding='utf-8')

    def test_cpr_is_read_from_the_same_encoder_file_and_not_duplicated(self):
        self.write()
        with patch.object(self.module, 'Node', Mock()) as node:
            self.module._nodes(self.context)
        self.assertEqual(node.call_count, 2)
        encoder, odom = [call.kwargs for call in node.call_args_list]
        self.assertEqual(encoder['parameters'], [str(self.encoder_file), {'use_sim_time': False}])
        self.assertEqual(odom['parameters'], [str(self.odom_file), {
            'left_counts_per_revolution': 4000.0, 'right_counts_per_revolution': 3000.0}, {'publish_tf': False, 'use_sim_time': False}])

    def test_invalid_geometry_or_cpr_is_rejected_before_any_node_action(self):
        for kind in ('geometry', 'calibration'):
            with self.subTest(kind=kind):
                self.odom['wheel_odometry']['ros__parameters']['wheel_separation'] = 0 if kind == 'geometry' else .54
                self.encoder['roboclaw_encoder']['ros__parameters']['left_counts_per_revolution'] = 0 if kind == 'calibration' else 4000.0
                self.write()
                with patch.object(self.module, 'Node', Mock()) as node:
                    with self.assertRaises(ValueError):
                        self.module._nodes(self.context)
                    node.assert_not_called()


if __name__ == '__main__':
    unittest.main()
