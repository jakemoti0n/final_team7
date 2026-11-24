"""Wait for a fresh localized robot transform before starting navigation."""
import time
import json
from pathlib import Path

import rclpy
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

rclpy.init()
node = rclpy.create_node('limbo_boot_wait_for_localization')
buffer = Buffer()
listener = TransformListener(buffer, node)
try:
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.2)
        try:
            tf = buffer.lookup_transform('map', 'base_footprint', Time())
        except TransformException:
            continue
        age = node.get_clock().now().nanoseconds / 1e9 - Time.from_msg(tf.header.stamp).nanoseconds / 1e9
        try:
            saved = json.loads((Path.home()/'.local/state/limbo/corridor-pose.json').read_text())
            recent = 0 <= time.time()-saved['time'] <= 5 and saved.get('boot') == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except (OSError, ValueError, KeyError):
            recent = False
        if recent and -1.5 <= age <= 1.0:
            print('Localized transform available', flush=True)
            break
finally:
    node.destroy_node()
    rclpy.try_shutdown()
