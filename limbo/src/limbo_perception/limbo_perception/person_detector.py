"""
RGB-D 카메라로 사람을 검출·추적하고 미래 경로를 예측하는 노드.

ROS 입출력(구독, 발행, TF, 파라미터)과 YOLO 호출만 여기서 하고,
계산은 ROS 없이 테스트할 수 있는 모듈에 맡긴다.
"""

from dataclasses import dataclass
import json
import os
import threading
import time
from typing import Optional

from ament_index_python.packages import get_package_share_directory
import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import PointStamped
from limbo_interfaces.msg import FollowTarget, PersonPredictionArray
from limbo_perception import (appearance, geometry, intent, motion, tracking,
                              visualization)
from limbo_perception.messages import prediction_array
import message_filters
import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.duration import Duration
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
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
# 시험 기록용(JSON 문자열): frame마다 카메라 시각 t, YOLO 박스 [클래스, x1, y1, x2, y2, 신뢰도],
# 합친 뒤 남은 박스 [x1, y1, x2, y2, leg 여부]
BOXES_TOPIC = '/person_detector/boxes'
# 따라가기 대상(운용자) 판정 → follow 노드 (PROJECT.md 2-9). 등록·해제는 서비스
FOLLOW_TARGET_TOPIC = '/follow/target'
FOLLOW_ENROLL_SERVICE = '/follow/enroll'
FOLLOW_FORGET_SERVICE = '/follow/forget'

PUBLISH_QUEUE = 10
EXECUTOR_THREADS = 2
TF_WARN_PERIOD_SEC = 2.0
ENROLL_WAIT_SEC = 2.0  # 등록 서비스가 다음 카메라 프레임의 판정을 기다리는 상한


@dataclass
class Detection:
    box: tuple  # (x1, y1, x2, y2) pixel
    raw_track_id: int
    leg: bool = False  # 하반신 모델의 leg 클래스 박스


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
    # 따라가기 재식별용 겉모습 (appearance.py)
    base_point: Optional[PointStamped] = None
    track: Optional[tracking.TrackObservation] = None
    band_pixels: int = 0
    signature: Optional[np.ndarray] = None


class PersonDetector(Node):

    def __init__(self):
        super().__init__('person_detector')
        self._declare_parameters()

        self.bridge = CvBridge()
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.model = YOLO(self.model_path)
        used = {c: self.model.names.get(c) for c in self.yolo_classes}
        self.get_logger().info(
            f'모델 {self.model_path} 클래스 {used} '
            f'(전체 {len(self.model.names)}개), 입력 크기 {self.yolo_imgsz}')

        # 따라가기 운용자: 등록 서명은 파일에 남아 노드를 다시 띄워도 유지된다
        self.identity = appearance.OperatorIdentity(
            self.band_config, self.identity_config,
            signature=self._load_signature())
        self.follow_lock = threading.Lock()
        self.enroll_event = None     # 등록 요청이 들어오면 Event, 다음 프레임에서 처리
        self.enroll_result = (False, '')
        self.follow_pub = self.create_publisher(
            FollowTarget, FOLLOW_TARGET_TOPIC, PUBLISH_QUEUE)
        # 등록 서비스는 다음 카메라 프레임의 판정을 기다린다. 기본 콜백 그룹(상호 배제)에 두면 기다리는 동안
        # 카메라 콜백이 못 돌아 영영 안 온다 → 서비스만 다른 그룹 (실행기 스레드 2개 중 하나를 쓴다)
        self.service_group = MutuallyExclusiveCallbackGroup()
        self.create_service(Trigger, FOLLOW_ENROLL_SERVICE, self.on_enroll,
                            callback_group=self.service_group)
        self.create_service(Trigger, FOLLOW_FORGET_SERVICE, self.on_forget,
                            callback_group=self.service_group)
        if self.identity.enrolled:
            self.get_logger().info(f'운용자 등록 서명 불러옴: {self.enroll_file}')
        self.depth_jump_filter = geometry.DepthJumpFilter(
            jump_m=self.jump_reject_m)
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
        self.boxes_pub = self.create_publisher(
            String, BOXES_TOPIC, PUBLISH_QUEUE)

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
        self.model_path = self._resolve_model_path(
            p('yolo.model', 'yolo11n.pt').value)
        self.yolo_tracker = p('yolo.tracker', 'botsort.yaml').value
        # 사람으로 볼 클래스 번호. COCO 모델은 0(person)뿐, 하반신 모델은 0(person)·1(leg)
        self.yolo_classes = list(p('yolo.classes', [0]).value)
        # 추론 입력 크기(px). 모델을 학습한 크기에 맞춘다 (yolo11n 640, 하반신 모델 512)
        self.yolo_imgsz = p('yolo.imgsz', 640).value
        # 하반신 모델의 leg 클래스 번호와, 같은 사람의 person·leg 박스를 하나로 합치는 기준
        self.leg_class = p('merge.leg_class', 1).value
        self.leg_inside_ratio = p('merge.leg_inside_ratio', 0.7).value
        self.leg_iou = p('merge.leg_iou', 0.5).value
        self.leg_pair_gap_ratio = p('merge.leg_pair_gap_ratio', 1.5).value
        self.leg_pair_vertical_overlap = p(
            'merge.leg_pair_vertical_overlap', 0.5).value

        self.yolo_confidence = p('yolo.confidence', 0.3).value
        self.sync_queue_size = p('sync.queue_size', 5).value
        self.sync_slop = p('sync.slop', 0.03).value
        self.tf_timeout = Duration(seconds=p('tf_timeout', 0.1).value)
        # 화면 좌우 끝에 조금만 걸친 사람 박스는 depth가 뒤쪽 배경을 재므로 거리 계산에서 뺀다
        self.edge_margin_px = p('edge_margin_px', 2).value
        self.edge_min_width_px = p('edge_min_width_px', 40).value
        # 같은 트랙의 depth가 한 프레임에 이만큼 넘게 튀면 그 값을 버림 (3프레임 연속이면 채택)
        self.jump_reject_m = p('jump_reject_m', 1.0).value

        d = geometry.DepthConfig()
        self.depth_config = geometry.DepthConfig(
            roi_margin=p('depth.roi_margin', d.roi_margin).value,
            min_depth=p('depth.min_depth', d.min_depth).value,
            max_depth=p('depth.max_depth', d.max_depth).value,
            percentile=p('depth.percentile', d.percentile).value,
            leg_roi_margin_x=p(
                'depth.leg_roi_margin_x', d.leg_roi_margin_x).value,
            leg_percentile=p('depth.leg_percentile', d.leg_percentile).value,
            leg_radius=p('leg_radius', d.leg_radius).value,
            person_box_radius=p('person_box_radius', d.person_box_radius).value,
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

        # 따라가기 운용자 재식별 (appearance.py)
        self.enroll_file = os.path.expanduser(
            p('follow.enroll_file', '~/.limbo/follow_operator.json').value)
        b = appearance.BandConfig()
        self.band_config = appearance.BandConfig(
            hue_min=p('follow.band.hue_min', b.hue_min).value,
            hue_max=p('follow.band.hue_max', b.hue_max).value,
            sat_min=p('follow.band.sat_min', b.sat_min).value,
            val_min=p('follow.band.val_min', b.val_min).value,
            min_pixels=p('follow.band.min_pixels', b.min_pixels).value,
            depth_tol=p('follow.band.depth_tol', b.depth_tol).value,
        )
        c = appearance.IdentityConfig()
        self.identity_config = appearance.IdentityConfig(
            signature_min=p('follow.identity.signature_min', c.signature_min).value,
            hold_sec=p('follow.identity.hold_sec', c.hold_sec).value,
            lost_sec=p('follow.identity.lost_sec', c.lost_sec).value,
            gate_m=p('follow.identity.gate_m', c.gate_m).value,
            enroll_min_x=p('follow.identity.enroll_min_x', c.enroll_min_x).value,
            enroll_max_x=p('follow.identity.enroll_max_x', c.enroll_max_x).value,
            enroll_half_width=p(
                'follow.identity.enroll_half_width', c.enroll_half_width).value,
            signature_update=p(
                'follow.identity.signature_update', c.signature_update).value,
        )

    # ---- 따라가기 운용자 등록·판정 ----

    def _load_signature(self):
        try:
            data = json.load(open(self.enroll_file))
            return np.array(data['signature'], dtype=np.float32)
        except (OSError, ValueError, KeyError):
            return None

    def _save_signature(self):
        os.makedirs(os.path.dirname(self.enroll_file), exist_ok=True)
        json.dump({'signature': self.identity.signature.tolist(),
                   'bins': list(self.band_config.signature_bins),
                   'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')},
                  open(self.enroll_file, 'w'))

    def on_enroll(self, request, response):
        """로봇 앞에 선 밴드 찬 사람을 운용자로 등록한다. 판정은 다음 카메라 프레임에서 한다."""
        event = threading.Event()
        with self.follow_lock:
            self.enroll_event = event
        if not event.wait(ENROLL_WAIT_SEC):
            with self.follow_lock:
                self.enroll_event = None
            response.success, response.message = False, 'no_camera_frame'
            return response
        response.success, response.message = self.enroll_result
        self.get_logger().info(f'운용자 등록 {response.success}: {response.message}')
        return response

    def on_forget(self, request, response):
        with self.follow_lock:
            self.identity.forget()
        try:
            os.remove(self.enroll_file)
        except OSError:
            pass
        response.success, response.message = True, 'forgotten'
        self.get_logger().info('운용자 등록 해제')
        return response

    def _update_follow(self, results, current_time, stamp):
        """이번 프레임의 사람 트랙에서 운용자를 고르고 /follow/target을 낸다. 운용자 결과(없으면 None)를 돌려준다."""
        candidates = []
        by_id = {}
        for r in results:
            if r.track is None or r.base_point is None:
                continue
            candidates.append(appearance.Candidate(
                r.person_id, r.track.x, r.track.y, r.track.vx, r.track.vy,
                r.base_point.point.x, r.base_point.point.y,
                r.band_pixels, r.signature))
            by_id[r.person_id] = r

        with self.follow_lock:
            if self.enroll_event is not None:
                self.enroll_result = self.identity.enroll(candidates, current_time)
                if self.enroll_result[0]:
                    self._save_signature()
                self.enroll_event.set()
                self.enroll_event = None
            decision = self.identity.decide(candidates, current_time)

        msg = FollowTarget()
        msg.header.stamp = stamp
        msg.header.frame_id = self.odom_frame
        msg.enrolled = decision.enrolled
        msg.found = decision.found
        msg.person_id = int(decision.person_id)
        msg.position.x, msg.position.y = float(decision.x), float(decision.y)
        msg.velocity.x, msg.velocity.y = float(decision.vx), float(decision.vy)
        msg.reason = decision.reason
        msg.band_pixels = int(decision.band_pixels)
        msg.similarity = float(decision.similarity)
        msg.since_band_sec = float(decision.since_band_sec)
        msg.lost_sec = float(decision.lost_sec)
        self.follow_pub.publish(msg)
        return (by_id.get(decision.person_id), decision) if decision.found else (None, decision)

    def _appearance(self, frame_hsv, depth_image, box, depth):
        """박스 안에서 사람 깊이 ±tol 픽셀만 골라(깊이 마스크) 밴드 픽셀 수와 색 서명을 계산한다."""
        x1, y1, x2, y2 = box
        h, w = depth_image.shape[:2]
        x1, x2 = max(0, x1), min(w, x2)
        y1, y2 = max(0, y1), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return 0, None
        mask = appearance.depth_mask(
            depth_image[y1:y2, x1:x2], depth, self.band_config.depth_tol)
        hsv = frame_hsv[y1:y2, x1:x2]
        return (appearance.band_pixels(hsv, mask, self.band_config),
                appearance.color_signature(hsv, mask, self.band_config))

    @staticmethod
    def _resolve_model_path(path):
        """
        상대 경로가 이 패키지 share 폴더에 있으면 그 경로로 바꾼다 (예: models/leg_512.pt).

        없으면 그대로 둔다 (yolo11n.pt처럼 ultralytics가 찾거나 받는 이름).
        """
        if os.path.isabs(path):
            return path
        share_path = os.path.join(
            get_package_share_directory('limbo_perception'), path)
        return share_path if os.path.exists(share_path) else path

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
        # 운용자 밴드·색 서명은 HSV로 본다. 프레임당 한 번만 바꾼다 (320×240, 1 ms 미만)
        frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        matched_person_ids = set()
        results = []
        for detection in self._detect(frame, msg.header.stamp):
            result = self._process_detection(
                detection, depth_image, frame_hsv, msg.header.stamp,
                current_time, robot_xy, matched_person_ids)
            if result is None:
                continue
            results.append(result)
            visualization.draw_detection(
                annotated_frame, detection.box, detection.raw_track_id,
                result.person_id, result.distance, result.speed,
                visualization.display_state(
                    result.motion_state, result.approach_intent,
                    result.approach_duration))

        operator, decision = self._update_follow(
            results, current_time, msg.header.stamp)
        if operator is not None:
            visualization.draw_operator(
                annotated_frame, operator.detection.box, decision.reason,
                decision.band_pixels, decision.similarity)

        self._publish_predictions(
            [r.prediction for r in results if r.prediction is not None],
            msg.header.stamp)
        self._publish_approach_intent(
            any(r.approach_intent for r in results), current_time)
        self._publish_nearest(results)

        self.track_manager.cleanup(current_time)
        self.depth_jump_filter.cleanup(current_time)

        output_msg = self.bridge.cv2_to_imgmsg(annotated_frame, encoding='bgr8')
        output_msg.header = msg.header
        self.image_pub.publish(output_msg)

    def _detect(self, frame, stamp):
        """YOLO + BoT-SORT 결과 중 track ID가 붙은 사람 box만, 한 사람에 하나씩 반환한다."""
        result = self.model.track(
            source=frame,
            classes=self.yolo_classes,
            imgsz=self.yolo_imgsz,
            conf=self.yolo_confidence,
            persist=True,  # BoT-SORT가 이전 frame의 tracking 상태를 이어 쓰게 한다
            tracker=self.yolo_tracker,
            verbose=False,
        )[0]

        boxes = result.boxes
        if boxes is None or not boxes.is_track or boxes.id is None:
            return []

        raw_track_ids = boxes.id.int().cpu().tolist()
        classes = boxes.cls.int().cpu().tolist()
        xyxy = [tuple(int(v) for v in b) for b in boxes.xyxy.cpu().numpy()]
        kept = geometry.merge_leg_boxes(
            xyxy, classes, self.leg_class, self.leg_inside_ratio, self.leg_iou,
            self.leg_pair_gap_ratio, self.leg_pair_vertical_overlap)
        confs = boxes.conf.cpu().tolist()
        self.boxes_pub.publish(String(data=json.dumps({
            't': stamp.sec + stamp.nanosec * 1e-9,
            'boxes': [[c, *b, round(f, 3)]
                      for c, b, f in zip(classes, xyxy, confs)],
            'kept': [[*box, int(classes[i] == self.leg_class)]
                     for i, box in kept],
        })))
        return [Detection(box, raw_track_ids[i],
                          leg=classes[i] == self.leg_class)
                for i, box in kept]

    def _process_detection(self, detection, depth_image, frame_hsv, stamp,
                           current_time, robot_xy, matched_person_ids):
        """Depth → 3D → odom → Kalman → 움직임/의도/예측. depth가 없으면 None."""
        x1, y1, x2, y2 = detection.box
        if geometry.clipped_at_edge(
                detection.box, depth_image.shape[1],
                self.edge_margin_px, self.edge_min_width_px):
            self.get_logger().debug(
                f'화면 끝에 걸친 좁은 박스 {detection.box} 거리 계산 제외')
            return None
        depth = geometry.person_depth(
            depth_image, x1, y1, x2, y2, self.depth_config, leg=detection.leg)
        if depth is None:
            return None
        measured = depth
        depth, rejected = self.depth_jump_filter.update(
            detection.raw_track_id, depth, current_time)
        if rejected:
            self.get_logger().debug(
                f'트랙 {detection.raw_track_id} depth {measured:.2f} m 튐 → '
                f'직전 {depth:.2f} m 유지')

        u = (x1 + x2) / 2.0
        v = (y1 + y2) / 2.0
        x, y, z = geometry.pixel_to_optical_point(u, v, depth, self.intrinsics)
        # depth → 3D 직후에 민다: 카메라→사람 방향을 바로 아는 곳이고, 이후 base·odom 변환과
        # 추적·예측·nearest 위치 토픽이 모두 같은 보정된 점을 쓴다
        x, y, z = geometry.push_to_body_center(
            x, y, z,
            geometry.body_center_radius(self.depth_config, detection.leg))

        result = PersonResult(
            detection=detection,
            distance=np.sqrt(x * x + y * y + z * z),
            optical_point=self._point(self.camera_frame, stamp, x, y, z),
        )
        # 운용자 재식별용: 깊이는 보정 전 측정값(밴드·옷 픽셀의 depth와 같은 기준)
        result.band_pixels, result.signature = self._appearance(
            frame_hsv, depth_image, detection.box, depth)

        base_point = self._transform(result.optical_point, self.robot_frame)
        result.base_point = base_point
        result.odom_point = self._transform(
            result.optical_point, self.odom_frame)
        if result.odom_point is None:
            return result

        obs = self.track_manager.observe(
            detection.raw_track_id,
            result.odom_point.point.x, result.odom_point.point.y,
            current_time, matched_person_ids)
        result.person_id = obs.person_id
        result.track = obs
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
