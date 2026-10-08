"""
RGB-D 카메라로 사람을 검출·추적하고 미래 경로를 예측하는 노드.

ROS 입출력(구독, 발행, TF, 파라미터)과 YOLO 호출만 여기서 하고,
계산은 ROS 없이 테스트할 수 있는 모듈에 맡긴다.
"""

from dataclasses import dataclass
from typing import Optional

from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped
from limbo_interfaces.msg import PersonPredictionArray
from limbo_perception import geometry, intent, motion, tracking, visualization
from limbo_perception.messages import prediction_array
import message_filters
import numpy as np
import rclpy
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool
import tf2_geometry_msgs  # noqa: F401  PointStamped용 tf2 변환 등록
from tf2_ros import Buffer, TransformException, TransformListener
from ultralytics import YOLO
from visualization_msgs.msg import MarkerArray

# 다른 노드와의 계약이라 이름을 바꾸면 구독하는 쪽도 같이 바꿔야 한다
PREDICTIONS_TOPIC = '/person_detector/predictions'  # → human_layer
PREDICTED_PATHS_TOPIC = '/person_detector/predicted_paths'
ANNOTATED_IMAGE_TOPIC = '/person_detector/annotated_image'
APPROACH_INTENT_TOPIC = '/person_detector/approach_intent'
NEAREST_OPTICAL_TOPIC = '/person_detector/person_position'
NEAREST_BASE_TOPIC = '/person_detector/person_position_base'
NEAREST_ODOM_TOPIC = '/person_detector/person_position_odom'

PUBLISH_QUEUE = 10
YOLO_PERSON_CLASS = 0  # COCO
EXECUTOR_THREADS = 2
TF_WARN_PERIOD_SEC = 2.0


@dataclass
class Detection:
    box: tuple  # (x1, y1, x2, y2) pixel
    raw_track_id: int


@dataclass
class PersonResult:
    detection: Detection
    distance: float
    optical_point: PointStamped
    odom_point: Optional[PointStamped] = None
    person_id: Optional[int] = None
    speed: float = 0.0
    motion_state: str = 'WARMUP'
    approach_intent: bool = False
    approach_duration: float = 0.0
    prediction: Optional[motion.PredictedPerson] = None


class PersonDetector(Node):

    def __init__(self):
        super().__init__('person_detector')
        self._declare_parameters()

        self.bridge = CvBridge()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.model = YOLO(self.model_path)
        self.track_manager = tracking.TrackManager(
            self.tracker_config, logger=self.get_logger())
        self.intrinsics = None

        self.prediction_pub = self.create_publisher(
            PersonPredictionArray, PREDICTIONS_TOPIC, PUBLISH_QUEUE)
        self.prediction_marker_pub = self.create_publisher(
            MarkerArray, PREDICTED_PATHS_TOPIC, PUBLISH_QUEUE)
        self.image_pub = self.create_publisher(
            Image, ANNOTATED_IMAGE_TOPIC, PUBLISH_QUEUE)
        self.approach_intent_pub = self.create_publisher(
            Bool, APPROACH_INTENT_TOPIC, PUBLISH_QUEUE)
        self.person_position_pub = self.create_publisher(
            PointStamped, NEAREST_OPTICAL_TOPIC, PUBLISH_QUEUE)
        self.person_base_pub = self.create_publisher(
            PointStamped, NEAREST_BASE_TOPIC, PUBLISH_QUEUE)
        self.person_odom_pub = self.create_publisher(
            PointStamped, NEAREST_ODOM_TOPIC, PUBLISH_QUEUE)

        # 같은 시점의 RGB와 depth를 짝지어 받아야 사람 위치가 어긋나지 않는다
        self.rgb_sub = message_filters.Subscriber(
            self, Image, self.rgb_topic, qos_profile=qos_profile_sensor_data)
        self.depth_sub = message_filters.Subscriber(
            self, Image, self.depth_topic,
            qos_profile=qos_profile_sensor_data)
        self.rgb_depth_sync = message_filters.ApproximateTimeSynchronizer(
            [self.rgb_sub, self.depth_sub],
            queue_size=self.sync_queue_size, slop=self.sync_slop)
        self.rgb_depth_sync.registerCallback(self.image_callback)

        self.create_subscription(
            CameraInfo, self.camera_info_topic, self.camera_info_callback,
            qos_profile_sensor_data)

        self.get_logger().info('Person detector with RGB-D depth started')

    def _declare_parameters(self):
        # 코드 기본값은 yaml 없이도 노드가 뜨게 하는 보험이다. 튜닝은 yaml에서 한다.
        p = self.declare_parameter

        self.rgb_topic = p('rgb_topic', '/rgbd_camera/image').value
        self.depth_topic = p('depth_topic', '/rgbd_camera/depth_image').value
        self.camera_info_topic = p(
            'camera_info_topic', '/rgbd_camera/camera_info').value
        self.robot_frame = p('robot_frame', 'base_link').value
        self.odom_frame = p('odom_frame', 'odom').value
        self.camera_frame = p('camera_frame', 'rgbd_camera_optical_link').value
        self.model_path = p('yolo.model', 'yolo11n.pt').value
        self.yolo_tracker = p('yolo.tracker', 'botsort.yaml').value

        self.yolo_confidence = p('yolo.confidence', 0.3).value
        self.sync_queue_size = p('sync.queue_size', 5).value
        self.sync_slop = p('sync.slop', 0.03).value
        self.tf_timeout = Duration(seconds=p('tf_timeout', 0.1).value)

        d = geometry.DepthConfig()
        self.depth_config = geometry.DepthConfig(
            roi_margin=p('depth.roi_margin', d.roi_margin).value,
            min_depth=p('depth.min_depth', d.min_depth).value,
            max_depth=p('depth.max_depth', d.max_depth).value,
        )

        t = tracking.TrackerConfig()
        self.tracker_config = tracking.TrackerConfig(
            reassociate_max_age=p(
                'tracking.reassociate_max_age', t.reassociate_max_age).value,
            reassociate_max_distance=p(
                'tracking.reassociate_max_distance',
                t.reassociate_max_distance).value,
            max_position_jump=p(
                'tracking.max_position_jump', t.max_position_jump).value,
            min_track_hits=p(
                'tracking.min_track_hits', t.min_track_hits).value,
            track_timeout=p('tracking.track_timeout', t.track_timeout).value,
            stop_window=p('tracking.stop_window', t.stop_window).value,
            stop_max_displacement=p(
                'tracking.stop_max_displacement', t.stop_max_displacement).value,
            kalman_measurement_noise=p(
                'tracking.kalman_measurement_noise',
                t.kalman_measurement_noise).value,
            kalman_process_noise=p(
                'tracking.kalman_process_noise', t.kalman_process_noise).value,
        )

        m = motion.MotionConfig()
        self.motion_config = motion.MotionConfig(
            stationary_speed_threshold=p(
                'motion.stationary_speed_threshold',
                m.stationary_speed_threshold).value,
            approach_speed_threshold=p(
                'motion.approach_speed_threshold',
                m.approach_speed_threshold).value,
        )

        pr = motion.PredictionConfig()
        self.prediction_config = motion.PredictionConfig(
            horizon=p('prediction.horizon', pr.horizon).value,
            dt=p('prediction.dt', pr.dt).value,
        )

        i = intent.IntentConfig()
        self.intent_config = intent.IntentConfig(
            interaction_min_x=p(
                'intent.interaction_min_x', i.interaction_min_x).value,
            interaction_max_x=p(
                'intent.interaction_max_x', i.interaction_max_x).value,
            interaction_half_width=p(
                'intent.interaction_half_width',
                i.interaction_half_width).value,
            approach_hold_time=p(
                'intent.approach_hold_time', i.approach_hold_time).value,
            intent_min_hold_time=p(
                'intent.intent_min_hold_time', i.intent_min_hold_time).value,
            intent_lost_grace_time=p(
                'intent.intent_lost_grace_time',
                i.intent_lost_grace_time).value,
        )

    def camera_info_callback(self, msg):
        self.intrinsics = geometry.CameraIntrinsics.from_k(msg.k)

    def image_callback(self, msg, depth_msg):
        if self.intrinsics is None:
            return

        depth_image = self.bridge.imgmsg_to_cv2(
            depth_msg, desired_encoding='passthrough')
        robot_xy = self._robot_position(msg.header.stamp)
        # 사람이 검출되지 않는 frame에서도 cleanup이 동작해야 해서 먼저 계산한다
        current_time = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        annotated_frame = frame.copy()

        matched_person_ids = set()
        results = []
        for detection in self._detect(frame):
            result = self._process_detection(
                detection, depth_image, msg.header.stamp, current_time,
                robot_xy, matched_person_ids)
            if result is None:
                continue
            results.append(result)
            visualization.draw_detection(
                annotated_frame, detection.box, detection.raw_track_id,
                result.person_id, result.distance, result.speed,
                visualization.display_state(
                    result.motion_state, result.approach_intent,
                    result.approach_duration))

        self._publish_predictions(
            [r.prediction for r in results if r.prediction is not None],
            msg.header.stamp)
        self._publish_approach_intent(
            any(r.approach_intent for r in results), current_time)
        self._publish_nearest(results)

        self.track_manager.cleanup(current_time)

        output_msg = self.bridge.cv2_to_imgmsg(annotated_frame, encoding='bgr8')
        output_msg.header = msg.header
        self.image_pub.publish(output_msg)

    def _detect(self, frame):
        """YOLO + BoT-SORT 결과 중 track ID가 붙은 사람 box만 반환한다."""
        result = self.model.track(
            source=frame,
            classes=[YOLO_PERSON_CLASS],
            conf=self.yolo_confidence,
            persist=True,  # BoT-SORT가 이전 frame의 tracking 상태를 이어 쓰게 한다
            tracker=self.yolo_tracker,
            verbose=False,
        )[0]

        boxes = result.boxes
        if boxes is None or not boxes.is_track or boxes.id is None:
            return []

        raw_track_ids = boxes.id.int().cpu().tolist()
        detections = []
        for box, raw_track_id in zip(boxes, raw_track_ids):
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            detections.append(Detection(
                (int(x1), int(y1), int(x2), int(y2)), raw_track_id))
        return detections

    def _process_detection(self, detection, depth_image, stamp, current_time,
                           robot_xy, matched_person_ids):
        """Depth → 3D → odom → Kalman → 움직임/의도/예측. depth가 없으면 None."""
        x1, y1, x2, y2 = detection.box
        depth = geometry.person_depth(
            depth_image, x1, y1, x2, y2, self.depth_config)
        if depth is None:
            return None

        u = (x1 + x2) / 2.0
        v = (y1 + y2) / 2.0
        x, y, z = geometry.pixel_to_optical_point(u, v, depth, self.intrinsics)

        result = PersonResult(
            detection=detection,
            distance=np.sqrt(x * x + y * y + z * z),
            optical_point=self._point(self.camera_frame, stamp, x, y, z),
        )

        base_point = self._transform(result.optical_point, self.robot_frame)
        result.odom_point = self._transform(
            result.optical_point, self.odom_frame)
        if result.odom_point is None:
            return result

        obs = self.track_manager.observe(
            detection.raw_track_id,
            result.odom_point.point.x, result.odom_point.point.y,
            current_time, matched_person_ids)
        result.person_id = obs.person_id
        result.speed = float(np.sqrt(obs.vx * obs.vx + obs.vy * obs.vy))

        if not obs.stable:
            return result

        result.prediction = motion.PredictedPerson(
            track_id=obs.person_id,
            current_x=obs.x, current_y=obs.y, vx=obs.vx, vy=obs.vy,
            points=motion.predict_trajectory(
                obs.x, obs.y, obs.vx, obs.vy, self.prediction_config))

        if robot_xy is not None:
            result.motion_state, _ = motion.classify_person_motion(
                obs.x, obs.y, obs.vx, obs.vy, robot_xy[0], robot_xy[1],
                self.motion_config)

        if base_point is not None:
            result.approach_intent, result.approach_duration = (
                intent.update_approach_intent(
                    self.track_manager.tracks.get(obs.person_id),
                    result.motion_state,
                    base_point.point.x, base_point.point.y,
                    current_time, self.intent_config))

        return result

    def _publish_predictions(self, predictions, stamp):
        # 예측은 그 카메라 사진을 찍은 시각 기준이다. 노드 시계를 안 쓰면 sim time(/clock 구독)이 필요 없어진다
        self.prediction_marker_pub.publish(
            visualization.prediction_markers(
                predictions, self.odom_frame, stamp))
        self.prediction_pub.publish(
            prediction_array(predictions, self.odom_frame, stamp))

    def _publish_approach_intent(self, detected_now, current_time):
        msg = Bool()
        msg.data = detected_now or intent.any_recent_confirmed_intent(
            self.track_manager.tracks.values(), current_time,
            self.intent_config)
        self.approach_intent_pub.publish(msg)

    def _publish_nearest(self, results):
        """tracking은 모든 사람에게 하지만 위치 토픽은 기존대로 가장 가까운 한 명만."""
        if not results:
            return
        nearest = min(results, key=lambda r: r.distance)

        self.person_position_pub.publish(nearest.optical_point)

        base_point = self._transform(nearest.optical_point, self.robot_frame)
        if base_point is not None:
            self.person_base_pub.publish(base_point)

        # odom 변환은 사람별 처리에서 이미 했으므로 다시 조회하지 않는다
        if nearest.odom_point is not None:
            self.person_odom_pub.publish(nearest.odom_point)

    @staticmethod
    def _point(frame_id, stamp, x, y, z):
        msg = PointStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        msg.point.x = float(x)
        msg.point.y = float(y)
        msg.point.z = float(z)
        return msg

    def _robot_position(self, stamp):
        """로봇 원점의 odom 좌표 (x, y), TF 실패 시 None."""
        origin = self._transform(
            self._point(self.robot_frame, stamp, 0.0, 0.0, 0.0),
            self.odom_frame)
        if origin is None:
            return None
        return origin.point.x, origin.point.y

    def _transform(self, point_msg, target_frame):
        try:
            return self.tf_buffer.transform(
                point_msg, target_frame, timeout=self.tf_timeout)
        except TransformException as ex:
            self.get_logger().warn(
                f'TF transform failed {point_msg.header.frame_id} -> '
                f'{target_frame}: {ex}',
                throttle_duration_sec=TF_WARN_PERIOD_SEC)
            return None


def main(args=None):
    rclpy.init(args=args)
    node = PersonDetector()
    executor = MultiThreadedExecutor(num_threads=EXECUTOR_THREADS)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()

    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
