#!/usr/bin/env python3
"""Suppress small, isolated near-depth patches in the real OAK costmap input."""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def clean_near_depth(depth_mm, max_speckle_pixels):
    """Remove small connected patches in the optical 0–1 m obstacle band."""
    # Extra range allows an object crossing the costmap's 1 m depth cutoff
    # to count its connected pixels on both sides of the cutoff.
    support = np.where(depth_mm <= 1200, depth_mm, 0).astype(np.int16)
    cv2.filterSpeckles(support, 0, max_speckle_pixels, 50)
    # A single scanline can contain many false near pixels. An agreeing 3x3
    # median rejects such lines without replacing any measurement by a new depth.
    local_median = cv2.medianBlur(support, 3)
    inconsistent = np.abs(support - local_median) > 50
    cleaned = depth_mm.copy()
    cleaned[(depth_mm <= 1000) & ((support == 0) | inconsistent)] = 0
    return cleaned


def confirm_small_patches(cleaned, previous, max_speckle_pixels):
    """Confirm smaller patches in two observations; keep large surfaces immediately."""
    near = np.where(cleaned <= 1200, cleaned, 0).astype(np.int16)
    large = near.copy()
    cv2.filterSpeckles(large, 0, max_speckle_pixels * 8, 50)
    y, x = np.nonzero((near > 0) & (near <= 1000) & (large == 0))
    out = cleaned.copy()
    if not len(x):
        return out, near

    accepted = np.zeros(len(x), dtype=bool)
    if previous is not None:
        # A 6-pixel radius allows modest motion between 10 Hz observations.
        # Bins avoid allocating a full image for each candidate pixel.
        bins = near[y, x] // 50
        kernel = np.ones((13, 13), dtype=np.uint8)
        for band in np.unique(bins):
            lo = max(1, int(band) * 50 - 75)
            hi = (int(band) + 1) * 50 + 75
            matches = cv2.inRange(previous, lo, hi)
            nearby = cv2.dilate(matches, kernel)
            selected = bins == band
            accepted[selected] = nearby[y[selected], x[selected]] != 0
    out[y[~accepted], x[~accepted]] = 0
    return out, near


class NearDepthFilter(Node):
    def __init__(self):
        super().__init__('real_near_depth_filter')
        self.max_pixels = self.declare_parameter('max_speckle_pixels', 128).value
        if self.max_pixels < 1:
            raise ValueError('max_speckle_pixels must be positive')
        self.bridge = CvBridge()
        self.previous = None
        self.last_stamp = None
        self.output = self.create_publisher(Image, 'depth_out', 2)
        self.create_subscription(Image, 'depth_in', self.filter_image, qos_profile_sensor_data)

    def filter_image(self, image):
        if image.encoding != '16UC1':
            self.get_logger().error('Expected unsigned 16-bit OAK depth in mm', throttle_duration_sec=5)
            return
        depth = self.bridge.imgmsg_to_cv2(image, desired_encoding='passthrough')
        stamp = image.header.stamp.sec * 1_000_000_000 + image.header.stamp.nanosec
        recent = self.last_stamp is not None and 0 < stamp - self.last_stamp <= 250_000_000
        previous = self.previous if recent and self.previous.shape == depth.shape else None
        spatial = clean_near_depth(depth, self.max_pixels)
        measured, self.previous = confirm_small_patches(spatial, previous, self.max_pixels)
        self.last_stamp = stamp
        result = self.bridge.cv2_to_imgmsg(measured, encoding='16UC1')
        result.header = image.header
        self.output.publish(result)


def main():
    rclpy.init()
    node = NearDepthFilter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
