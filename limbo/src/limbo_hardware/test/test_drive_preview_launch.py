"""Shared calibration loading: changing the source files changes the preview."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

path = Path(__file__).resolve().parents[1] / 'launch/drive_preview.launch.py'
spec = importlib.util.spec_from_file_location('drive_preview_launch', path)
launch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch_module)


class PreviewLaunchTests(unittest.TestCase):
    def test_shared_calibration_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            enc = Path(directory) / 'enc.yaml'
            odom = Path(directory) / 'odom.yaml'
            enc.write_text(yaml.safe_dump({'roboclaw_encoder': {'ros__parameters': {
                'left_counts_per_revolution': 4000, 'right_counts_per_revolution': 3000}}}))
            geometry = {'left_wheel_radius': .08, 'right_wheel_radius': .07, 'wheel_separation': .55}
            odom.write_text(yaml.safe_dump({'wheel_odometry': {'ros__parameters': geometry}}))
            values = launch_module.load_shared_parameters(str(enc), str(odom))
            self.assertEqual(values, dict(geometry, left_counts_per_revolution=4000., right_counts_per_revolution=3000.))
            for bad in (0, -1, True, float('nan'), float('inf'), '.54'):
                geometry['wheel_separation'] = bad
                odom.write_text(yaml.safe_dump({'wheel_odometry': {'ros__parameters': geometry}}))
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    launch_module.load_shared_parameters(str(enc), str(odom))


if __name__ == '__main__':
    unittest.main()
