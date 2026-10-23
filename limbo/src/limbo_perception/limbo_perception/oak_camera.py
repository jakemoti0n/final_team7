"""
OAK-D Lite를 직접 열어 컬러·깊이·CameraInfo와 카메라 안 모델(하반신 leg_640)의 검출 결과를 발행하는 노드.

Gazebo 카메라와 같은 토픽 이름(/rgbd_camera/*)으로 내므로 person_detector는 카메라 출처를 모른다.
검출 결과는 /oak/detections로 내고, person_detector가 detector.source: oak이면 YOLO 대신 이것을 쓴다.
장치는 한 프로세스만 열 수 있어 카메라를 쓰는 것은 모두 이 노드를 거친다.

장치를 못 찾거나 링크가 끊기면(X_LINK_ERROR, 케이블 빠짐, 장치 재부팅) 노드는 살아 있고 장치만 다시 연다.
연결돼 있는데 NN 결과가 stall_timeout 넘게 안 오면 멈춘 것으로 보고 다시 연다.

네 토픽은 같은 stamp를 단다(NN에 들어간 그 프레임의 촬영 시각). 시각은 노드 시계(sim이면 /clock)에서
장치 지연만큼 뺀 값이라 시뮬레이션 TF와도, 실물 벽시계와도 맞는다.
"""

import os
import sys
import threading
import time

from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from limbo_perception import oak
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

# person_detector가 구독하는 토픽 (Gazebo 브리지와 같은 이름)
IMAGE_TOPIC = '/rgbd_camera/image'
DEPTH_TOPIC = '/rgbd_camera/depth_image'
CAMERA_INFO_TOPIC = '/rgbd_camera/camera_info'
DETECTIONS_TOPIC = '/oak/detections'

QUEUE_SIZE = 4        # 장치 출력 큐. 밀리면 오래된 것을 버린다
POLL_SEC = 0.002
STATS_PERIOD_SEC = 10.0


class DeviceStalled(RuntimeError):
    """연결은 살아 있는데 장치에서 결과가 안 온다."""


class OakCamera(Node):

    def __init__(self):
        super().__init__('oak_camera')
        p = self.declare_parameter
        self.frame_id = p('frame_id', 'rgbd_camera_optical_link').value
        self.blob_path = self._resolve(p('blob', 'models/leg_640_352_3shave.blob').value)
        # USB 2.0 케이블이면 high. 2.0 케이블에 super를 주면 8초 뒤 워치독 크래시로 장치가 꺼진다 (변경 기록 45)
        self.usb_speed = p('usb_speed', 'high').value
        self.nn_threads = p('nn.threads', 2).value
        self.confidence = p('nn.confidence', 0.3).value
        self.iou = p('nn.iou', 0.5).value
        # 끊기면 다시 연결. false면 예전처럼 exit code 1로 끝난다(런치 respawn 등 바깥에서 다시 띄울 때)
        self.reconnect = p('reconnect.enabled', True).value
        self.backoff = oak.ReconnectBackoff(
            p('reconnect.min_delay', 1.0).value, p('reconnect.max_delay', 10.0).value)
        self.stall_timeout = p('stall_timeout', 3.0).value  # sec

        self.bridge = CvBridge()
        self.image_pub = self.create_publisher(Image, IMAGE_TOPIC, qos_profile_sensor_data)
        self.depth_pub = self.create_publisher(Image, DEPTH_TOPIC, qos_profile_sensor_data)
        self.info_pub = self.create_publisher(
            CameraInfo, CAMERA_INFO_TOPIC, qos_profile_sensor_data)
        self.detections_pub = self.create_publisher(
            Detection2DArray, DETECTIONS_TOPIC, qos_profile_sensor_data)

        self.matcher = oak.FrameMatcher()
        self.camera_info = None
        self.counts = {'published': 0, 'no_depth': 0}
        self.latencies = []
        self.stop = threading.Event()
        self.failed = False
        self.frames_since_connect = 0
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    @staticmethod
    def _resolve(path):
        if os.path.isabs(path):
            return path
        return os.path.join(get_package_share_directory('limbo_perception'), path)

    def _run(self):
        import depthai as dai

        speed = dai.UsbSpeed.HIGH if self.usb_speed == 'high' else dai.UsbSpeed.SUPER
        lost_at = None    # 끊긴 시각 (monotonic). 다시 붙었을 때 얼마나 끊겼는지 알린다
        attempt = 0
        while not self.stop.is_set() and rclpy.ok():
            try:
                self._connect_and_stream(dai, speed, lost_at)
                return    # 노드가 끝나서 빠져나옴
            except RuntimeError as ex:
                # 장치를 못 찾거나, 케이블이 빠지거나, 장치가 재부팅되거나, 결과가 멈추면 여기로 온다
                if not self.reconnect:
                    self.get_logger().error(f'OAK 장치 오류: {ex}')
                    self.failed = True
                    rclpy.try_shutdown()
                    return
                if self.frames_since_connect:
                    # 영상을 받던 연결이 끊긴 것이므로 끊김을 처음부터 센다
                    lost_at, attempt = None, 0
                    self.frames_since_connect = 0
                if lost_at is None:
                    lost_at = time.monotonic()
                attempt += 1
                delay = self.backoff.next_delay()
                self.get_logger().warn(
                    f'OAK 장치 오류: {ex} → {delay:.0f}초 뒤 다시 연결 ({attempt}번째)')
                self.stop.wait(delay)

    def _connect_and_stream(self, dai, speed, lost_at):
        pipeline = oak.build_pipeline(
            with_depth=True, blob_path=self.blob_path, threads=self.nn_threads)
        self.frames_since_connect = 0
        with dai.Device(pipeline, speed) as dev:
            again = '' if lost_at is None else \
                f' (다시 연결, 끊긴 지 {time.monotonic() - lost_at:.0f}초)'
            self.get_logger().info(
                f'{dev.getDeviceName()} 연결 | USB {dev.getUsbSpeed().name} | '
                f'blob {self.blob_path}{again}')
            k, distortion = oak.preview_intrinsics(dev.readCalibration())
            self.camera_info = self._camera_info(k, distortion)
            # 장치를 다시 열면 sequence 번호가 처음부터라 전 연결의 남은 프레임을 버린다
            self.matcher = oak.FrameMatcher()
            self.counts = {k: 0 for k in self.counts}
            self.latencies = []
            self._loop(dev, dai)

    def _loop(self, dev, dai):
        queues = {name: dev.getOutputQueue(name, QUEUE_SIZE, False)
                  for name in ('rgb', 'nn', 'depth')}
        t_stats = time.monotonic()
        t_last_nn = time.monotonic()
        while not self.stop.is_set() and rclpy.ok():
            got = False
            for depth in queues['depth'].tryGetAll():
                self.matcher.add_depth(depth.getTimestamp().total_seconds(), depth)
                got = True
            for frame in queues['rgb'].tryGetAll():
                self._handle(self.matcher.add_frame(
                    frame.getSequenceNum(), frame.getTimestamp().total_seconds(), frame), dai)
                got = True
            for nn in queues['nn'].tryGetAll():
                self._handle(self.matcher.add_result(nn.getSequenceNum(), nn), dai)
                t_last_nn = time.monotonic()
                got = True
            if time.monotonic() - t_last_nn > self.stall_timeout:
                raise DeviceStalled(f'NN 결과가 {self.stall_timeout:.0f}초 넘게 안 옴')
            if time.monotonic() - t_stats >= STATS_PERIOD_SEC:
                self._log_stats(dev, time.monotonic() - t_stats)
                t_stats = time.monotonic()
            if not got:
                time.sleep(POLL_SEC)

    def _handle(self, matched, dai):
        if matched is None:
            return
        _, frame, nn, depth = matched
        if depth is None:
            self.counts['no_depth'] += 1
            return
        # 장치가 찍은 뒤 지금까지 걸린 시간만큼 노드 시계를 되돌려 촬영 시각으로 쓴다
        latency = (dai.Clock.now() - frame.getTimestamp()).total_seconds()
        stamp = (self.get_clock().now() - Duration(seconds=latency)).to_msg()

        image_msg = self.bridge.cv2_to_imgmsg(frame.getCvFrame(), encoding='bgr8')
        # REP 118: 16UC1 깊이는 mm. person_detector가 encoding을 보고 m로 바꾼다
        depth_msg = self.bridge.cv2_to_imgmsg(
            oak.crop_depth(depth.getFrame()).copy(), encoding='16UC1')
        for msg in (image_msg, depth_msg, self.camera_info):
            msg.header.stamp = stamp
            msg.header.frame_id = self.frame_id
        detections = self._detections(oak.decode(nn, self.confidence, self.iou), image_msg.header)

        self.image_pub.publish(image_msg)
        self.depth_pub.publish(depth_msg)
        self.info_pub.publish(self.camera_info)
        self.detections_pub.publish(detections)
        self.counts['published'] += 1
        self.latencies.append(latency)
        if self.frames_since_connect == 0:
            self.backoff.reset()
        self.frames_since_connect += 1

    def _camera_info(self, k, distortion):
        msg = CameraInfo()
        msg.width, msg.height = oak.WIDTH, oak.HEIGHT
        msg.k = [float(v) for v in k.flatten()]
        msg.p = [float(k[0, 0]), 0.0, float(k[0, 2]), 0.0,
                 0.0, float(k[1, 1]), float(k[1, 2]), 0.0,
                 0.0, 0.0, 1.0, 0.0]
        msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        # 영상은 왜곡을 펴지 않은 원본이다. 계수는 참고용으로 싣는다(앞 8개, OpenCV rational 순서)
        msg.distortion_model = 'rational_polynomial'
        msg.d = [float(v) for v in distortion[:8]]
        return msg

    @staticmethod
    def _detections(dets, header):
        msg = Detection2DArray()
        msg.header = header
        for x1, y1, x2, y2, score, cls in dets:
            d = Detection2D()
            d.header = header
            d.bbox.center.position.x = float(x1 + x2) / 2.0
            d.bbox.center.position.y = float(y1 + y2) / 2.0
            d.bbox.size_x = float(x2 - x1)
            d.bbox.size_y = float(y2 - y1)
            hypothesis = ObjectHypothesisWithPose()
            hypothesis.hypothesis.class_id = str(int(cls))
            hypothesis.hypothesis.score = float(score)
            d.results.append(hypothesis)
            msg.detections.append(d)
        return msg

    def _log_stats(self, dev, seconds):
        lat = sorted(self.latencies)
        median_ms = lat[len(lat) // 2] * 1000 if lat else float('nan')
        self.get_logger().info(
            f'{seconds:.0f}초: 발행 {self.counts["published"] / seconds:.1f} Hz, '
            f'깊이 짝 없음 {self.counts["no_depth"]}장 | 지연 중앙값 {median_ms:.0f} ms | '
            f'칩 온도 {dev.getChipTemperature().average:.0f}°C')
        self.counts = {k: 0 for k in self.counts}
        self.latencies = []

    def destroy_node(self):
        self.stop.set()
        self.thread.join(timeout=2.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = OakCamera()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
    if node.failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
