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

        self.bridge = CvBridge()

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
        #       'x': odom_x,
        #       'y': odom_y,
        #       'time': timestamp,
        #       'vx': vx,
        #       'vy': vy
        #   }
        # }
        self.track_states = {}

        # ID switch / 이상치 방어
        self.max_position_jump = 0.8

        # 최소 몇 frame 살아남아야 신뢰할지
        self.min_track_hits = 5

        # 이 시간 이상 안 보이면 track 제거
        self.track_timeout = 1.0


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

        current_time = self.stamp_to_sec(
            msg.header.stamp
        )

        frame = self.bridge.imgmsg_to_cv2(
            msg,
            desired_encoding='bgr8'
        )


        # ==============================
        # YOLO
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


        nearest_person = None
        nearest_distance = float('inf')


        # ==============================
        # 모든 사람 처리
        # ==============================

        if (
            result.boxes is None
            or not result.boxes.is_track
            or result.boxes.id is None
        ):
            track_ids = []
        else:
            track_ids = (
                result.boxes.id
                .int()
                .cpu()
                .tolist()
            )

        for box, track_id in zip(
            result.boxes,
            track_ids
        ):

            vx = 0.0
            vy = 0.0
            speed = 0.0
            stable = False

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
            #
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
            # Bounding box 표시
            # ==============================

            cv2.rectangle(
                annotated_frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            if stable:
                state_text = 'TRACK'
            else:
                state_text = 'WARMUP'

            text = (
                    f'ID:{track_id} '
                    f'{distance:.2f}m '
                    f'v:{speed:.2f}m/s'
                    f'{state_text}'
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
            # ==============================

            if distance < nearest_distance:

                nearest_distance = distance

                nearest_person = (
                    X,
                    Y,
                    Z
                )


        # ==============================
        # 가장 가까운 사람 위치 publish
        # ==============================

        if nearest_person is not None:

            X, Y, Z = nearest_person

            point_msg = PointStamped()

            point_msg.header.stamp = Time()

            # 위의 XYZ 계산은 optical coordinate convention
            point_msg.header.frame_id = (
                'rgbd_camera_optical_link'
            )

            point_msg.point.x = float(X)
            point_msg.point.y = float(Y)
            point_msg.point.z = float(Z)

            self.person_position_pub.publish(
                point_msg
            )

            # ==============================
            # Camera -> base_link
            # ==============================

            base_point = self.transform_point(
                point_msg,
                'base_link'
            )

            if base_point is not None:

                self.person_base_pub.publish(
                    base_point
                )


            # ==============================
            # Camera -> odom
            # ==============================

            odom_point = self.transform_point(
                point_msg,
                'odom'
            )

            if odom_point is not None:
                ox = odom_point.point.x
                oy = odom_point.point.y

                filtered_x, filtered_y, vx, vy, stable = (
                    self.update_person_track(
                        track_id,
                        ox,
                        oy,
                        current_time
                    )
                )

                speed = np.sqrt(
                    vx * vx +
                    vy * vy
                )
                            
                # ==============================
                # 현재 상태 저장
                # ==============================

                self.person_odom_pub.publish(
                    odom_point
                )

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
                'hits': 1
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
        if dt <= 0.001 or dt > 1.0:

            track['kalman'] = PersonKalmanFilter(
                measured_x,
                measured_y
            )

            track['last_time'] = current_time
            track['last_seen'] = current_time
            track['hits'] = 1

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

            # 이상한 측정으로 기존 Kalman을 망가뜨리지 않고
            # 해당 ID를 새 track처럼 재시작
            track['kalman'] = PersonKalmanFilter(
                measured_x,
                measured_y
            )

            track['last_time'] = current_time
            track['last_seen'] = current_time
            track['hits'] = 1

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

        for track_id, track in self.track_states.items():

            if (
                current_time
                - track['last_seen']
                > self.track_timeout
            ):
                remove_ids.append(track_id)


        for track_id in remove_ids:

            del self.track_states[track_id]


def main(args=None):

    rclpy.init(args=args)

    node = PersonDetector()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    node.destroy_node()

    rclpy.shutdown()


if __name__ == '__main__':
    main()