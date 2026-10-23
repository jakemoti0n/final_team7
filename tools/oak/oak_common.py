"""OAK-D Lite 점검 도구 공통 코드: 명령줄 공통 인자, 지연, 그림.

파이프라인·모델 출력 풀기·카메라 구성 설명은 ROS 노드(oak_camera)와 같이 쓰도록
limbo/src/limbo_perception/limbo_perception/oak.py에 있다. 여기서는 그것을 그대로 가져다 쓴다.
"""
import argparse
import os
import sys

import cv2
import depthai as dai

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO, 'limbo', 'src', 'limbo_perception'))
from limbo_perception.oak import (  # noqa: E402,F401  점검 도구들이 oc.이름으로 쓴다
    CLASS_NAMES, DEPTH_HEIGHT, DEPTH_WIDTH, FPS, HEIGHT, WIDTH, build_pipeline, decode)

DEFAULT_BLOB = os.path.join(_REPO, 'limbo', 'src', 'limbo_perception', 'models', 'leg_640_352_3shave.blob')


def add_common_args(parser):
    parser.add_argument('--usb', choices=['high', 'super'], default='high',
                        help='USB 링크 속도. USB 2.0 케이블이면 high(기본). 기본값 그대로 두면 2.0 케이블에서 워치독 크래시가 난다')
    parser.add_argument('--seconds', type=float, default=10, help='측정 시간(초)')
    return parser


def usb_speed(name):
    return dai.UsbSpeed.HIGH if name == 'high' else dai.UsbSpeed.SUPER


def latency_ms(msg):
    """장치가 프레임을 찍은 시각부터 지금까지(ms)."""
    return (dai.Clock.now() - msg.getTimestamp()).total_seconds() * 1000


def draw(frame, dets):
    for x1, y1, x2, y2, score, cls in dets:
        color = (0, 255, 0) if int(cls) == 0 else (0, 200, 255)
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(frame, f'{CLASS_NAMES[int(cls)]} {score:.2f}', (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return frame
