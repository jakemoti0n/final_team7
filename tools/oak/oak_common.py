"""OAK-D Lite 공통 코드: 파이프라인 만들기, 모델 출력 풀기, 명령줄 공통 인자.

카메라 구성은 실물 배치와 같다(2026-10-23 결정).
- 컬러: 1080p 센서 모드 → ISP 1/3 → 640x360 → preview 640x352 (16:9, 가로 69°·세로 41°). 하반신 모델 입력과 같은 크기.
- 깊이: 모노 640x480 두 개로 스테레오, 컬러(CAM_A)에 정렬, 640x360, 단위 mm(uint16).
- 모델: leg_640을 640x352 입력으로 변환한 blob. 출력 (1, 6, 4620) = [cx, cy, w, h, person 점수, leg 점수] × 후보 4620개.
  카메라 안에서는 NMS를 안 하므로 호스트에서 decode()로 걸러 쓴다.
- shave: 스테레오를 같이 돌리면 NN에 shave 7개만 남는다. 3 shave × 2 thread 블롭이 14.8 Hz로 가장 빨랐다(6·7 shave는 10 Hz).
"""
import argparse
import os

import cv2
import depthai as dai
import numpy as np

WIDTH, HEIGHT = 640, 352           # 모델 입력 = 컬러 preview 크기
DEPTH_WIDTH, DEPTH_HEIGHT = 640, 360
FPS = 20
CLASS_NAMES = {0: 'person', 1: 'leg'}
DEFAULT_BLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'leg_640_352_3shave.blob')


def add_common_args(parser):
    parser.add_argument('--usb', choices=['high', 'super'], default='high',
                        help='USB 링크 속도. USB 2.0 케이블이면 high(기본). 기본값 그대로 두면 2.0 케이블에서 워치독 크래시가 난다')
    parser.add_argument('--seconds', type=float, default=10, help='측정 시간(초)')
    return parser


def usb_speed(name):
    return dai.UsbSpeed.HIGH if name == 'high' else dai.UsbSpeed.SUPER


def build_pipeline(with_depth=True, blob_path=None, threads=2):
    """컬러(+깊이)(+NN) 파이프라인. 출력 스트림 이름: 'rgb', 'depth', 'nn' (만든 것만)."""
    p = dai.Pipeline()
    cam = p.create(dai.node.ColorCamera)
    cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
    cam.setIspScale(1, 3)
    cam.setPreviewSize(WIDTH, HEIGHT)
    cam.setInterleaved(False)
    cam.setFps(FPS)

    if with_depth:
        left, right = p.create(dai.node.MonoCamera), p.create(dai.node.MonoCamera)
        left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
        right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
        for mono in (left, right):
            mono.setResolution(dai.MonoCameraProperties.SensorResolution.THE_480_P)
            mono.setFps(FPS)
        stereo = p.create(dai.node.StereoDepth)
        stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.DEFAULT)
        stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
        stereo.setOutputSize(DEPTH_WIDTH, DEPTH_HEIGHT)
        left.out.link(stereo.left)
        right.out.link(stereo.right)
        _xout(p, 'depth', stereo.depth)

    if blob_path:
        nn = p.create(dai.node.NeuralNetwork)
        nn.setBlobPath(blob_path)
        nn.setNumInferenceThreads(threads)
        nn.input.setBlocking(False)
        nn.input.setQueueSize(1)      # 밀리면 오래된 프레임을 버려 지연이 쌓이지 않게
        cam.preview.link(nn.input)
        _xout(p, 'rgb', nn.passthrough)   # NN에 들어간 바로 그 프레임
        _xout(p, 'nn', nn.out)
    else:
        _xout(p, 'rgb', cam.preview)
    return p


def _xout(pipeline, name, source):
    x = pipeline.create(dai.node.XLinkOut)
    x.setStreamName(name)
    source.link(x.input)


def decode(nn_data, conf=0.3, iou=0.5):
    """NN 출력 → [x1, y1, x2, y2, 점수, 클래스] 배열 (픽셀 단위, NMS 뒤). 없으면 (0, 6)."""
    raw = np.array(nn_data.getLayerFp16('output0'), dtype=np.float32).reshape(6, -1)
    boxes, scores = raw[:4].T, raw[4:].T
    cls = scores.argmax(1)
    best = scores.max(1)
    keep = best > conf
    boxes, best, cls = boxes[keep], best[keep], cls[keep]
    if len(best) == 0:
        return np.zeros((0, 6))
    xywh = np.column_stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2, boxes[:, 2], boxes[:, 3]])
    idx = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), best.tolist(), conf, iou)).reshape(-1)
    xyxy = np.column_stack([xywh[:, 0], xywh[:, 1], xywh[:, 0] + xywh[:, 2], xywh[:, 1] + xywh[:, 3]])
    return np.column_stack([xyxy[idx], best[idx], cls[idx]])


def latency_ms(msg):
    """장치가 프레임을 찍은 시각부터 지금까지(ms)."""
    return (dai.Clock.now() - msg.getTimestamp()).total_seconds() * 1000


def draw(frame, dets):
    for x1, y1, x2, y2, score, cls in dets:
        color = (0, 255, 0) if int(cls) == 0 else (0, 200, 255)
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
        cv2.putText(frame, f'{CLASS_NAMES[int(cls)]} {score:.2f}', (int(x1), int(y1) - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return frame
