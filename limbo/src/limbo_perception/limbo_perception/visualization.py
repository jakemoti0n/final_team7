"""디버깅용 출력: 주석 이미지와 예측 경로 marker."""

import cv2
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray

BOX_COLOR = (0, 255, 0)
PATH_COLOR = (1.0, 0.5, 0.0, 1.0)  # r, g, b, a
PATH_WIDTH = 0.05
PATH_HEIGHT = 0.1
# 너무 오래 남지 않도록 marker lifetime 설정
PATH_LIFETIME_NSEC = 300000000


def display_state(motion_state, approach_intent, approach_duration):
    if approach_intent:
        return 'APPROACH_INTENT'
    if motion_state == 'APPROACHING' and approach_duration > 0.0:
        return 'CANDIDATE'
    return motion_state


def draw_detection(frame, box, raw_track_id, person_id, distance, speed,
                   state_text):
    """박스와 tracking 정보를 frame 위에 그린다."""
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 2)

    if person_id is not None:
        id_text = f'P:{person_id} B:{raw_track_id}'
    else:
        id_text = f'B:{raw_track_id}'

    text = f'ID:{id_text} {distance:.2f}m v:{speed:.2f}m/s {state_text}'
    cv2.putText(frame, text, (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, BOX_COLOR, 2)


def _point(x, y, z):
    point = Point()
    point.x = float(x)
    point.y = float(y)
    point.z = z
    return point


def prediction_markers(predictions, frame_id, stamp):
    """사람별 현재 위치 → 미래 예측점을 잇는 LINE_STRIP marker 배열."""
    marker_array = MarkerArray()

    for marker_id, person in enumerate(predictions):
        marker = Marker()
        marker.header.frame_id = frame_id
        marker.header.stamp = stamp
        marker.ns = 'predicted_paths'
        marker.id = marker_id
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.scale.x = PATH_WIDTH
        (marker.color.r, marker.color.g,
         marker.color.b, marker.color.a) = PATH_COLOR
        marker.lifetime.sec = 0
        marker.lifetime.nanosec = PATH_LIFETIME_NSEC

        marker.points.append(
            _point(person.current_x, person.current_y, PATH_HEIGHT))
        for future_x, future_y, _ in person.points:
            marker.points.append(_point(future_x, future_y, PATH_HEIGHT))

        marker_array.markers.append(marker)

    return marker_array
