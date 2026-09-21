import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge

from ultralytics import YOLO

from rclpy.duration import Duration

from tf2_ros import Buffer, TransformListener, TransformException
import tf2_geometry_msgs

from builtin_interfaces.msg import Time
from std_msgs.msg import Bool

from visualization_msgs.msg import Marker
from visualization_msgs.msg import MarkerArray

from geometry_msgs.msg import Point
import math

from limbo_interfaces.msg import (
    PersonPrediction,
    PersonPredictionArray
)

class PersonKalmanFilter:

    def __init__(self, x, y):

        # state:
        # [x, y, vx, vy]
        self.x = np.array([
            [x],
            [y],
            [0.0],
            [0.0]
        ], dtype=float)

        # 초기 covariance
        self.P = np.eye(4) * 1.0

        # measurement matrix
        # 우리는 x, y만 측정
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0]
        ])

        # measurement noise
        # RGB-D + YOLO 위치 흔들림
        self.R = np.eye(2) * 0.05


    def predict(self, dt):

        # constant velocity model
        self.F = np.array([
            [1.0, 0.0, dt,  0.0],
            [0.0, 1.0, 0.0, dt ],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ])

        # process noise
        q = 0.5

        self.Q = np.array([
            [dt**4 / 4, 0.0,        dt**3 / 2, 0.0],
            [0.0,        dt**4 / 4, 0.0,        dt**3 / 2],
            [dt**3 / 2, 0.0,        dt**2,      0.0],
            [0.0,        dt**3 / 2, 0.0,        dt**2]
        ]) * q

        self.x = self.F @ self.x

        self.P = (
            self.F
            @ self.P
            @ self.F.T
            + self.Q
        )


    def update(self, measured_x, measured_y):

        z = np.array([
            [measured_x],
            [measured_y]
        ])

        # innovation
        y = z - self.H @ self.x

        S = (
            self.H
            @ self.P
            @ self.H.T
            + self.R
        )

        K = (
            self.P
            @ self.H.T
            @ np.linalg.inv(S)
        )

        self.x = self.x + K @ y

        I = np.eye(4)

        self.P = (
            I - K @ self.H
        ) @ self.P


    def get_state(self):

        return (
            float(self.x[0, 0]),
            float(self.x[1, 0]),
            float(self.x[2, 0]),
            float(self.x[3, 0])
        )

class PersonDetector(Node):

    def __init__(self):
        super().__init__('person_detector')

        # humanCostmap을 발행하기 위한 publisher
        self.prediction_pub = self.create_publisher(
            PersonPredictionArray,
            '/person_detector/predictions',
            10
        )

        # 이 속도 이하면 정지 상태로 간주
        self.stationary_speed_threshold = 0.05

        # Limbo 방향 속도 성분이 이 이상이면 접근/이탈로 판단
        self.approach_speed_threshold = 0.03

        self.bridge = CvBridge()

        self.interaction_max_x = 2.0

        # 좌우 폭
        # base_link 기준 +Y 왼쪽, -Y 오른쪽
        self.interaction_half_width = 0.8

        # 너무 가까이 들어온 경우도 포함
        self.interaction_min_x = 0.3

        # APPROACHING이 이 시간 이상 지속되어야 intent 확정
        self.approach_hold_time = 0.5

        # ==============================
        # TF2
        # ==============================

        self.tf_buffer = Buffer()

        self.tf_listener = TransformListener(
            self.tf_buffer,
            self
        )

        # YOLO 모델
        self.model = YOLO('yolo11n.pt')

        # 가장 최근 Depth 이미지
        self.latest_depth = None

        # Camera intrinsic parameters
        self.fx = None
        self.fy = None
        self.cx = None
        self.cy = None

        # ==============
        # 경로 예측을 위한 파라미터 값
        # ==============
        self.prediction_horizon = 2.0
        self.prediction_dt = 0.25

        # 예측한 경로를 marker로 출력하기 위해 발행
        self.prediction_marker_pub = self.create_publisher(
            MarkerArray,
            '/person_detector/predicted_paths',
            10
        )


        # ==============================
        # RGB
        # ==============================

        self.rgb_sub = self.create_subscription(
            Image,
            '/rgbd_camera/image',
            self.image_callback,
            qos_profile_sensor_data
        )


        # ==============================
        # Depth
        # ==============================

        self.depth_sub = self.create_subscription(
            Image,
            '/rgbd_camera/depth_image',
            self.depth_callback,
            qos_profile_sensor_data
        )


        # ==============================
        # Camera Info
        # ==============================

        self.camera_info_sub = self.create_subscription(
            CameraInfo,
            '/rgbd_camera/camera_info',
            self.camera_info_callback,
            qos_profile_sensor_data
        )

        # Limbo 기준 사람 위치
        self.person_base_pub = self.create_publisher(
            PointStamped,
            '/person_detector/person_position_base',
            10
        )

        # odom 기준 사람 위치
        self.person_odom_pub = self.create_publisher(
            PointStamped,
            '/person_detector/person_position_odom',
            10
        )

        # ==============================
        # YOLO 결과 이미지
        # ==============================

        self.image_pub = self.create_publisher(
            Image,
            '/person_detector/annotated_image',
            10
        )


        # ==============================
        # 가장 가까운 사람 위치
        # ==============================

        self.person_position_pub = self.create_publisher(
            PointStamped,
            '/person_detector/person_position',
            10
        )

        self.get_logger().info(
            'Person detector with RGB-D depth started'
        )

        # ==============================
        # Tracking history
        # ==============================

        # {
        #   track_id: {
        #       'kalman': PersonKalmanFilter,
        #       'last_time': timestamp,
        #       'last_seen': timestamp,
        #       'hits': observation_count
        #   }
        # }
        self.track_states = {}

        # ============================================================
        # Track Manager
        # ============================================================

        # BoT-SORT ID → Limbo 내부 person ID
        self.raw_to_person_id = {}

        # Limbo 내부 person ID → 현재 연결된 BoT-SORT ID
        self.person_to_raw_id = {}

        # Limbo가 독립적으로 발급하는 ID
        self.next_person_id = 1

        # ID가 바뀌었을 때 기존 track과 재연결을 시도할 최대 시간
        self.reassociate_max_age = 3.0  # sec

        # Kalman 예상 위치와 새 detection 위치의 최대 허용 거리
        self.reassociate_max_distance = 0.50  # meter

        # ID switch / 이상치 방어
        self.max_position_jump = 0.8

        # 최소 몇 frame 살아남아야 신뢰할지
        self.min_track_hits = 5

        # 이 시간 이상 안 보이면 track 제거
        self.track_timeout = 3.0

        # ==============================
        # Approach Intent
        # ==============================

        self.approach_intent_pub = self.create_publisher(
            Bool,
            '/person_detector/approach_intent',
            10
        )

        # 잠깐 detection이 끊겨도 intent 유지
        self.intent_lost_grace_time = 1.0

        # intent 확정 후 최소 유지시간
        self.intent_min_hold_time = 2.0
    #---------------------------
    # 사람 움직임 분류 함수
    #---------------------------

    def classify_person_motion(
        self,
        person_x,
        person_y,
        vx,
        vy,
        robot_x,
        robot_y
    ):

        speed = np.sqrt(
            vx * vx +
            vy * vy
        )

        # ------------------------------
        # 거의 움직이지 않는 사람
        # ------------------------------
        if speed < self.stationary_speed_threshold:
            return 'STATIONARY', 0.0


        # 사람 -> Limbo 벡터
        dx = robot_x - person_x
        dy = robot_y - person_y

        distance = np.sqrt(
            dx * dx +
            dy * dy
        )

        if distance < 0.001:
            return 'STATIONARY', 0.0


        # 사람 -> Limbo 방향 단위벡터
        ux = dx / distance
        uy = dy / distance


        # 사람 속도가 Limbo 방향으로 얼마나 향하는지
        approach_speed = (
            vx * ux +
            vy * uy
        )


        if approach_speed > self.approach_speed_threshold:
            state = 'APPROACHING'

        elif approach_speed < -self.approach_speed_threshold:
            state = 'LEAVING'

        else:
            state = 'PASSING'


        return state, approach_speed

    # ============================================================
    # TF 변환 함수
    # ============================================================

    def transform_point(self, point_msg, target_frame):

        try:
            transformed = self.tf_buffer.transform(
                point_msg,
                target_frame,
                timeout=Duration(seconds=0.1)
            )

            return transformed

        except TransformException as ex:

            self.get_logger().warn(
                f'TF transform failed '
                f'{point_msg.header.frame_id} -> '
                f'{target_frame}: {ex}',
                throttle_duration_sec=2.0
            )

            return None

    def stamp_to_sec(self, stamp):

        return (
            float(stamp.sec)
            + float(stamp.nanosec) * 1e-9
        )

    # ============================================================
    # Camera calibration
    # ============================================================

    def camera_info_callback(self, msg):

        # CameraInfo K matrix
        #
        # [ fx  0 cx ]
        # [  0 fy cy ]
        # [  0  0  1 ]

        self.fx = msg.k[0]
        self.fy = msg.k[4]

        self.cx = msg.k[2]
        self.cy = msg.k[5]


    # ============================================================
    # Depth image
    # ============================================================

    def depth_callback(self, msg):

        self.latest_depth = self.bridge.imgmsg_to_cv2(
            msg,
            desired_encoding='passthrough'
        )


    # ============================================================
    # Bounding box 안에서 안정적인 depth 추출
    # ============================================================

    def get_person_depth(self, x1, y1, x2, y2):

        if self.latest_depth is None:
            return None

        height, width = self.latest_depth.shape[:2]

        # Bounding box 중앙 40% 정도만 사용
        # 가장자리에는 배경이 들어갈 가능성이 높기 때문
        box_width = x2 - x1
        box_height = y2 - y1

        rx1 = int(x1 + box_width * 0.30)
        rx2 = int(x2 - box_width * 0.30)

        ry1 = int(y1 + box_height * 0.30)
        ry2 = int(y2 - box_height * 0.30)

        # 이미지 범위를 벗어나지 않도록 제한
        rx1 = max(0, min(rx1, width - 1))
        rx2 = max(0, min(rx2, width))

        ry1 = max(0, min(ry1, height - 1))
        ry2 = max(0, min(ry2, height))

        if rx2 <= rx1 or ry2 <= ry1:
            return None

        depth_roi = self.latest_depth[
            ry1:ry2,
            rx1:rx2
        ]

        # 유효하지 않은 depth 제거
        valid_depth = depth_roi[
            np.isfinite(depth_roi) &
            (depth_roi > 0.1) &
            (depth_roi < 5.0)
        ]

        if len(valid_depth) == 0:
            return None

        # 평균보다는 median이 outlier에 강함
        depth = float(np.median(valid_depth))

        return depth


    # ============================================================
    # RGB + YOLO
    # ============================================================

    def image_callback(self, msg):

        if self.latest_depth is None:
            return

        if self.fx is None:
            return

        robot_origin = PointStamped()

        robot_origin.header.stamp = Time()
        robot_origin.header.frame_id = 'base_link'

        robot_origin.point.x = 0.0
        robot_origin.point.y = 0.0
        robot_origin.point.z = 0.0

        robot_odom_point = self.transform_point(
            robot_origin,
            'odom'
        )

        robot_x = None
        robot_y = None


        if robot_odom_point is not None:

            robot_x = robot_odom_point.point.x
            robot_y = robot_odom_point.point.y

        # callback 시작 시 항상 현재 시간을 만들어 둔다.
        # 사람이 검출되지 않는 frame에서도 cleanup_tracks()가 동작해야 한다.
        current_time = self.stamp_to_sec(
            msg.header.stamp
        )

        frame = self.bridge.imgmsg_to_cv2(
            msg,
            desired_encoding='bgr8'
        )

        # ==============================
        # YOLO + BoT-SORT
        # ==============================

        results = self.model.track(
            source=frame,

            # COCO class 0 = person
            classes=[0],

            conf=0.3,

            # 이전 frame의 tracking 상태 유지
            persist=True,

            # BoT-SORT 사용
            tracker='botsort.yaml',

            verbose=False
        )

        result = results[0]
        annotated_frame = frame.copy()

        # 기존 ROS topic들은 "가장 가까운 사람" 한 명을 publish하도록 유지한다.
        nearest_distance = float('inf')
        nearest_point_msg = None
        nearest_odom_point = None

        any_approach_intent = False
        # ==============================
        # Tracking 가능한 box / ID 준비
        # ==============================

        if (
            result.boxes is None
            or not result.boxes.is_track
            or result.boxes.id is None
        ):
            boxes = []
            raw_track_ids = []
        else:
            boxes = result.boxes
            raw_track_ids = (
                result.boxes.id
                .int()
                .cpu()
                .tolist()
            )

        # ==============================
        # 모든 사람 개별 처리
        #
        # 중요:
        # 각 사람마다
        # Depth -> 3D -> odom -> Kalman -> speed
        # 순서까지 끝낸 뒤 화면에 표시한다.
        # ==============================

        prediction_data = []
        matched_person_ids = set()


        for box, raw_track_id in zip(
            boxes,
            raw_track_ids
        ):
            person_id = None

            # TF 또는 tracking이 한 frame 실패해도
            # 화면 표시 코드가 죽지 않도록 기본값 설정
            vx = 0.0
            vy = 0.0
            speed = 0.0
            stable = False

            motion_state = 'WARMUP'
            approach_speed = 0.0
            approach_intent = False
            approach_duration = 0.0

            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

            x1 = int(x1)
            y1 = int(y1)
            x2 = int(x2)
            y2 = int(y2)

            confidence = float(
                box.conf[0].cpu().numpy()
            )

            # ==============================
            # 사람 Depth
            # ==============================

            depth = self.get_person_depth(
                x1, y1, x2, y2
            )

            if depth is None:
                continue

            # Bounding box 중심 pixel
            u = (x1 + x2) / 2.0
            v = (y1 + y2) / 2.0

            # ==============================
            # Pixel + Depth -> 3D
            #
            # ROS optical frame:
            # X = right
            # Y = down
            # Z = forward
            # ==============================

            Z = depth

            X = (
                (u - self.cx)
                * Z
                / self.fx
            )

            Y = (
                (v - self.cy)
                * Z
                / self.fy
            )

            # 실제 카메라와의 직선거리
            distance = np.sqrt(
                X * X +
                Y * Y +
                Z * Z
            )

            # ==============================
            # 현재 사람의 optical-frame Point
            # ==============================

            point_msg = PointStamped()

            # Gazebo simulation에서는 latest TF를 사용
            point_msg.header.stamp = Time()
            point_msg.header.frame_id = (
                'rgbd_camera_optical_link'
            )

            point_msg.point.x = float(X)
            point_msg.point.y = float(Y)
            point_msg.point.z = float(Z)

            base_point = self.transform_point(
                point_msg,
                'base_link'
            )

            person_base_x = None
            person_base_y = None

            if base_point is not None:

                person_base_x = base_point.point.x
                person_base_y = base_point.point.y

            # ==============================
            # Camera -> odom
            #
            # 모든 사람을 각각 odom으로 변환한 뒤
            # ID별 Kalman tracking을 수행한다.
            # ==============================

            odom_point = self.transform_point(
                point_msg,
                'odom'
            )

            if odom_point is not None:

                ox = odom_point.point.x
                oy = odom_point.point.y

                current_time_sec = current_time

                person_id = self.resolve_person_id(
                    raw_track_id=raw_track_id,
                    measured_x=ox,
                    measured_y=oy,
                    current_time_sec=current_time_sec,
                    matched_person_ids=matched_person_ids
                )

                matched_person_ids.add(person_id)

                filtered_x, filtered_y, vx, vy, stable = (
                    self.update_person_track(
                        person_id,
                        ox,
                        oy,
                        current_time
                    )
                )

                speed = float(
                    np.sqrt(
                        vx * vx +
                        vy * vy
                    )
                )

                track_state = self.track_states[person_id]

                track_state['manager_x'] = filtered_x
                track_state['manager_y'] = filtered_y
                track_state['manager_vx'] = vx
                track_state['manager_vy'] = vy
                track_state['manager_last_seen'] = current_time_sec

                if stable:

                    predicted_points = self.predict_trajectory(
                        filtered_x,
                        filtered_y,
                        vx,
                        vy
                    )

                    prediction_data.append(
                        {
                            'track_id': person_id,
                            'current_x': filtered_x,
                            'current_y': filtered_y,
                            'points': predicted_points,
                            'vx': vx,
                            'vy': vy
                        }
                    )

                if (
                    stable
                    and robot_x is not None
                    and robot_y is not None
                ):

                    motion_state, approach_speed = (
                        self.classify_person_motion(
                            filtered_x,
                            filtered_y,
                            vx,
                            vy,
                            robot_x,
                            robot_y
                        )
                    )

                # self.get_logger().info(
                #     f'DISPLAY ID={track_id} '
                #     f'vx={vx:.3f}, vy={vy:.3f}, '
                #     f'speed={speed:.3f}'
                # )

                if (
                    stable
                    and person_base_x is not None
                    and person_base_y is not None
                ):

                    approach_intent, approach_duration = (
                        self.update_approach_intent(
                            person_id,
                            motion_state,
                            person_base_x,
                            person_base_y,
                            current_time
                        )
                    )
                    if approach_intent:
                        any_approach_intent = True

            # ==============================
            # Bounding box + tracking 정보 표시
            #
            # 반드시 Kalman / speed 계산 "이후"에 그린다.
            # ==============================

            cv2.rectangle(
                annotated_frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            if approach_intent:
                display_state = 'APPROACH_INTENT'
            elif (
                motion_state == 'APPROACHING'
                and approach_duration > 0.0
            ):
                display_state = 'CANDIDATE'
            else:
                display_state = motion_state

            if person_id is not None:
                id_text = f'P:{person_id} B:{raw_track_id}'
            else:
                id_text = f'B:{raw_track_id}'

            text = (
                f'ID:{id_text} '
                f'{distance:.2f}m '
                f'v:{speed:.2f}m/s '
                f'{display_state}'
            )

            cv2.putText(
                annotated_frame,
                text,
                (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2
            )

            # ==============================
            # 가장 가까운 사람 선택
            #
            # tracking은 모든 사람에게 수행하지만,
            # 기존 person_position/base/odom topic은
            # 가장 가까운 사람 한 명만 publish한다.
            # ==============================

            if distance < nearest_distance:

                nearest_distance = distance
                nearest_point_msg = point_msg
                nearest_odom_point = odom_point

        self.publish_predicted_paths(
            prediction_data
        )

        self.publish_prediction_data(
            prediction_data
        )

        for track_id, track in self.track_states.items():

            # intent가 확정된 track만 검사
            if not track.get('intent_confirmed', False):
                continue

            time_since_seen = (
                current_time
                - track['last_seen']
            )

            # 잠깐 detection이 끊긴 것은 허용
            if time_since_seen <= self.intent_lost_grace_time:
                any_approach_intent = True

        intent_msg = Bool()
        intent_msg.data = any_approach_intent

        self.approach_intent_pub.publish(
            intent_msg
        )


        # ==============================
        # 가장 가까운 사람 위치 publish
        # ==============================

        if nearest_point_msg is not None:

            # optical frame
            self.person_position_pub.publish(
                nearest_point_msg
            )

            # Camera -> base_link
            base_point = self.transform_point(
                nearest_point_msg,
                'base_link'
            )

            if base_point is not None:
                self.person_base_pub.publish(
                    base_point
                )

            # odom은 위의 각 사람 처리 과정에서 이미 계산한 값을 재사용
            if nearest_odom_point is not None:
                self.person_odom_pub.publish(
                    nearest_odom_point
                )

        # 사람이 보이지 않는 frame에서도 오래된 track을 정리한다.
        self.cleanup_tracks(current_time)

        # ==============================
        # Annotated image publish
        # ==============================

        output_msg = self.bridge.cv2_to_imgmsg(
            annotated_frame,
            encoding='bgr8'
        )

        output_msg.header = msg.header

        self.image_pub.publish(
            output_msg
        )

    def update_person_track(
        self,
        track_id,
        measured_x,
        measured_y,
        current_time
    ):

        # =========================================
        # 처음 보는 ID
        # =========================================

        if track_id not in self.track_states:

            kalman = PersonKalmanFilter(
                measured_x,
                measured_y
            )

            self.track_states[track_id] = {
                'kalman': kalman,
                'last_time': current_time,
                'last_seen': current_time,
                'hits': 1,
                'approach_start_time': None,
                'intent_confirmed': False,
                'intent_confirmed_time': None
            }

            return (
                measured_x,
                measured_y,
                0.0,
                0.0,
                False
            )


        track = self.track_states[track_id]

        dt = current_time - track['last_time']

        # 시간 이상치 방어
        if dt <= 0.001 or dt > 3.0:

            self.get_logger().warn(
                f'KF RESET TIME: '
                f'ID={track_id}, dt={dt:.3f}'
            )

            track['kalman'] = PersonKalmanFilter(
                measured_x,
                measured_y
            )

            track['last_time'] = current_time
            track['last_seen'] = current_time
            track['hits'] = 1
            track['approach_start_time'] = None

            return (
                measured_x,
                measured_y,
                0.0,
                0.0,
                False
            )


        kalman = track['kalman']


        # =========================================
        # 1. 이전 상태로부터 현재 위치 예측
        # =========================================

        kalman.predict(dt)

        predicted_x, predicted_y, _, _ = (
            kalman.get_state()
        )


        # =========================================
        # 2. 실제 측정과 예측 위치 차이
        # =========================================

        jump = np.sqrt(
            (measured_x - predicted_x) ** 2
            +
            (measured_y - predicted_y) ** 2
        )


        # =========================================
        # 3. ID switch / 순간이동 의심
        # =========================================

        if jump > self.max_position_jump:

            self.get_logger().warn(
                f'Possible ID switch: '
                f'ID={track_id}, '
                f'jump={jump:.2f}m'
            )

            self.get_logger().warn(
                f'KF RESET JUMP: '
                f'ID={track_id}, jump={jump:.2f}'
            )

            # 이상한 측정으로 기존 Kalman을 망가뜨리지 않고
            # 해당 ID를 새 track처럼 재시작
            track['kalman'] = PersonKalmanFilter(
                measured_x,
                measured_y
            )

            track['last_time'] = current_time
            track['last_seen'] = current_time
            track['hits'] = 1
            track['approach_start_time'] = None

            return (
                measured_x,
                measured_y,
                0.0,
                0.0,
                False
            )


        # =========================================
        # 4. 정상 측정이면 Kalman update
        # =========================================

        kalman.update(
            measured_x,
            measured_y
        )

        x, y, vx, vy = kalman.get_state()

        # self.get_logger().info(
        #     f'KF ID={track_id} '
        #     f'dt={dt:.3f} '
        #     f'measured=({measured_x:.2f}, {measured_y:.2f}) '
        #     f'filtered=({x:.2f}, {y:.2f}) '
        #     f'v=({vx:.3f}, {vy:.3f})'
        # )

        track['last_time'] = current_time
        track['last_seen'] = current_time
        track['hits'] += 1


        # 아직 충분히 관측되지 않은 track은 신뢰하지 않음
        stable = (
            track['hits']
            >= self.min_track_hits
        )


        return (
            x,
            y,
            vx,
            vy,
            stable
        )

    def cleanup_tracks(self, current_time):

        remove_ids = []

        # ========================================================
        # 1. timeout된 Limbo person_id 찾기
        # ========================================================
        for person_id, track in self.track_states.items():

            if (
                current_time
                - track['last_seen']
                > self.track_timeout
            ):
                remove_ids.append(person_id)

        # ========================================================
        # 2. track + Track Manager mapping 같이 삭제
        # ========================================================
        for person_id in remove_ids:

            # person_id와 현재 연결된 BoT-SORT raw ID 찾기
            raw_track_id = self.person_to_raw_id.pop(
                person_id,
                None
            )

            # raw ID → person ID mapping 삭제
            if raw_track_id is not None:

                if (
                    self.raw_to_person_id.get(raw_track_id)
                    == person_id
                ):
                    del self.raw_to_person_id[raw_track_id]

            # 혹시 남아 있는 stale mapping이 있다면 같이 제거
            stale_raw_ids = [
                raw_id
                for raw_id, mapped_person_id
                in self.raw_to_person_id.items()
                if mapped_person_id == person_id
            ]

            for raw_id in stale_raw_ids:
                del self.raw_to_person_id[raw_id]

            # 마지막으로 실제 Kalman / track 상태 삭제
            del self.track_states[person_id]

    def update_approach_intent(
        self,
        track_id,
        motion_state,
        person_base_x,
        person_base_y,
        current_time
    ):

        track = self.track_states.get(track_id)

        if track is None:
            return False, 0.0


        # =========================================
        # Interaction Zone
        # =========================================

        in_zone = (
            self.interaction_min_x
            <= person_base_x
            <= self.interaction_max_x
            and
            abs(person_base_y)
            <= self.interaction_half_width
        )


        # =========================================
        # 이미 intent가 확정된 사람
        # =========================================

        if track['intent_confirmed']:

            confirmed_duration = (
                current_time
                - track['intent_confirmed_time']
            )

            # 사람이 zone 안에 있다면
            # 멈췄더라도 intent 유지
            if in_zone:

                return True, confirmed_duration


            # 최소 hold time 동안은 바로 끄지 않음
            if confirmed_duration < self.intent_min_hold_time:

                return True, confirmed_duration


            # 충분히 시간이 지난 뒤 zone 밖이면 해제
            track['intent_confirmed'] = False
            track['intent_confirmed_time'] = None
            track['approach_start_time'] = None

            return False, 0.0


        # =========================================
        # 아직 intent가 확정되지 않은 사람
        # =========================================

        candidate = (
            motion_state == 'APPROACHING'
            and in_zone
        )


        if not candidate:

            track['approach_start_time'] = None

            return False, 0.0


        # 처음 candidate가 됨
        if track['approach_start_time'] is None:

            track['approach_start_time'] = current_time

            return False, 0.0


        duration = (
            current_time
            - track['approach_start_time']
        )


        # =========================================
        # 접근 의도 확정
        # =========================================

        if duration >= self.approach_hold_time:

            track['intent_confirmed'] = True
            track['intent_confirmed_time'] = current_time

            return True, duration


        return False, duration

    def predict_trajectory(
        self,
        x,
        y,
        vx,
        vy
    ):
        predicted_points = []

        t = self.prediction_dt

        while t <= self.prediction_horizon:

            future_x = x + vx * t
            future_y = y + vy * t

            predicted_points.append(
                (
                    future_x,
                    future_y,
                    t
                )
            )

            t += self.prediction_dt

        return predicted_points

    def publish_predicted_paths(
        self,
        prediction_data
    ):

        marker_array = MarkerArray()

        marker_id = 0

        for person in prediction_data:

            # =====================================
            # 예측 경로 선
            # =====================================

            line_marker = Marker()

            line_marker.header.frame_id = 'odom'
            line_marker.header.stamp = (
                self.get_clock()
                .now()
                .to_msg()
            )

            line_marker.ns = 'predicted_paths'
            line_marker.id = marker_id

            marker_id += 1

            line_marker.type = Marker.LINE_STRIP
            line_marker.action = Marker.ADD


            # 선 굵기
            line_marker.scale.x = 0.05


            # Marker 색상
            line_marker.color.r = 1.0
            line_marker.color.g = 0.5
            line_marker.color.b = 0.0
            line_marker.color.a = 1.0


            # 너무 오래 남지 않도록 lifetime 설정
            line_marker.lifetime.sec = 0
            line_marker.lifetime.nanosec = 300000000


            # =====================================
            # 현재 사람 위치부터 시작
            # =====================================

            current_point = Point()

            current_point.x = float(
                person['current_x']
            )

            current_point.y = float(
                person['current_y']
            )

            current_point.z = 0.1

            line_marker.points.append(
                current_point
            )


            # =====================================
            # 미래 예측점 추가
            # =====================================

            for future_x, future_y, t in person['points']:

                point = Point()

                point.x = float(
                    future_x
                )

                point.y = float(
                    future_y
                )

                point.z = 0.1

                line_marker.points.append(
                    point
                )


            marker_array.markers.append(
                line_marker
            )


        self.prediction_marker_pub.publish(
            marker_array
        )

    def publish_prediction_data(
        self,
        prediction_data
    ):
        msg = PersonPredictionArray()

        # 이 prediction의 좌표계는 odom
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'odom'

        for person in prediction_data:

            prediction = PersonPrediction()

            # Limbo Track Manager가 관리하는 안정적인 person ID
            prediction.person_id = int(
                person['track_id']
            )

            # 현재 위치
            prediction.current_position.x = float(
                person['current_x']
            )
            prediction.current_position.y = float(
                person['current_y']
            )
            prediction.current_position.z = 0.0

            # 현재 추정 속도
            prediction.velocity.x = float(
                person['vx']
            )
            prediction.velocity.y = float(
                person['vy']
            )
            prediction.velocity.z = 0.0

            # 미래 예측 위치
            for future_x, future_y, t in person['points']:

                point = Point()

                point.x = float(future_x)
                point.y = float(future_y)
                point.z = 0.0

                prediction.predicted_positions.append(
                    point
                )

                prediction.time_offsets.append(
                    float(t)
                )

            msg.predictions.append(
                prediction
            )

        self.prediction_pub.publish(
            msg
        )    

    def resolve_person_id(
        self,
        raw_track_id,
        measured_x,
        measured_y,
        current_time_sec,
        matched_person_ids
    ):
        """
        BoT-SORT의 raw_track_id를
        Limbo 내부 person_id로 변환한다.

        1. 기존 raw ID가 정상적으로 이어지고 있으면 그대로 사용
        2. raw ID가 바뀌었으면 Kalman 예상 위치와 비교해서 기존 person과 재연결
        3. 연결할 사람이 없으면 새로운 person_id 생성
        """

        raw_track_id = int(raw_track_id)

        # ========================================================
        # 1. 기존 BoT-SORT ID가 이미 연결되어 있는 경우
        # ========================================================

        if raw_track_id in self.raw_to_person_id:

            person_id = self.raw_to_person_id[raw_track_id]

            if (
                person_id in self.track_states
                and person_id not in matched_person_ids
            ):
                state = self.track_states[person_id]

                if (
                    'manager_x' in state
                    and 'manager_last_seen' in state
                ):
                    age = (
                        current_time_sec
                        - state['manager_last_seen']
                    )

                    if 0.0 <= age <= self.reassociate_max_age:

                        predicted_x = (
                            state['manager_x']
                            + state['manager_vx'] * age
                        )

                        predicted_y = (
                            state['manager_y']
                            + state['manager_vy'] * age
                        )

                        distance = math.hypot(
                            measured_x - predicted_x,
                            measured_y - predicted_y
                        )

                        # raw ID도 같고 위치도 정상적이면
                        # 기존 person 유지
                        if distance <= self.reassociate_max_distance:
                            return person_id

        # ========================================================
        # 2. raw ID가 바뀌었거나 위치가 이상한 경우
        #
        # 최근에 봤던 모든 Limbo person 중에서
        # Kalman 예상 위치가 가장 가까운 사람을 찾는다.
        # ========================================================

        best_person_id = None
        best_distance = float('inf')

        for person_id, state in self.track_states.items():

            # 현재 frame에서 이미 다른 detection에 할당된 사람은 제외
            if person_id in matched_person_ids:
                continue

            if (
                'manager_x' not in state
                or 'manager_last_seen' not in state
            ):
                continue

            age = (
                current_time_sec
                - state['manager_last_seen']
            )

            # 너무 오래 전에 사라진 사람은 재연결하지 않음
            if age < 0.0 or age > self.reassociate_max_age:
                continue

            # Constant Velocity 모델로 현재 위치 예상
            predicted_x = (
                state['manager_x']
                + state['manager_vx'] * age
            )

            predicted_y = (
                state['manager_y']
                + state['manager_vy'] * age
            )

            distance = math.hypot(
                measured_x - predicted_x,
                measured_y - predicted_y
            )

            if (
                distance <= self.reassociate_max_distance
                and distance < best_distance
            ):
                best_distance = distance
                best_person_id = person_id

        # ========================================================
        # 3. 기존 사람과 재연결 성공
        # ========================================================

        if best_person_id is not None:

            old_raw_id = self.person_to_raw_id.get(
                best_person_id
            )

            # 이전 BoT-SORT ID mapping 제거
            if old_raw_id is not None:
                if (
                    self.raw_to_person_id.get(old_raw_id)
                    == best_person_id
                ):
                    del self.raw_to_person_id[old_raw_id]

            # 새로운 BoT-SORT ID를 기존 Limbo person에 연결
            self.raw_to_person_id[raw_track_id] = best_person_id
            self.person_to_raw_id[best_person_id] = raw_track_id

            if old_raw_id != raw_track_id:
                self.get_logger().info(
                    f'[TRACK MANAGER] '
                    f'BoT-SORT ID {old_raw_id} -> {raw_track_id}, '
                    f'keep person_id={best_person_id}, '
                    f'distance={best_distance:.2f}m'
                )

            return best_person_id

        # ========================================================
        # 4. 기존 사람과 연결 불가능
        # → 완전히 새로운 사람
        # ========================================================

        new_person_id = self.next_person_id
        self.next_person_id += 1

        self.raw_to_person_id[raw_track_id] = new_person_id
        self.person_to_raw_id[new_person_id] = raw_track_id

        self.get_logger().info(
            f'[TRACK MANAGER] '
            f'New person_id={new_person_id}, '
            f'raw_track_id={raw_track_id}'
        )

        return new_person_id


def main(args=None):

    rclpy.init(args=args)

    node = PersonDetector()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()

    if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()