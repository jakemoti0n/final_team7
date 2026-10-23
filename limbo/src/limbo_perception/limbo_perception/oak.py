"""
OAK-D Lite 장치 쪽 코드: 파이프라인, 카메라 안 모델 출력 풀기, 프레임 짝짓기 (ROS 의존 없음).

oak_camera 노드와 tools/oak의 점검 도구가 같이 쓴다. depthai는 파이프라인을 만들 때만 import해서
장치가 없는 컴퓨터에서도 decode·FrameMatcher를 시험할 수 있다.

카메라 구성은 실물 배치와 같다(2026-10-23 결정, 변경 기록 45).
- 컬러: 1080p 센서 모드 → ISP 1/3 → 640x360 → preview 640x352 (16:9, 가로 69°·세로 41°).
  하반신 모델 입력과 같은 크기.
  preview는 ISP 화면의 위아래를 4 px씩 잘라 만든다.
- 깊이: 모노 640x480 두 개로 스테레오, 컬러(CAM_A)에 정렬, 640x360, 단위 mm(uint16).
- 모델: leg_640을 640x352 입력으로 변환한 blob.
  출력 (1, 6, 4620) = [cx, cy, w, h, person 점수, leg 점수] × 후보 4620개.
  카메라 안에서는 NMS를 안 하므로 호스트에서 decode()로 걸러 쓴다.
- shave: 스테레오를 같이 돌리면 NN에 shave 7개만 남는다. 3 shave × 2 thread 블롭이 14.8 Hz로 가장 빨랐다(6·7 shave는 10 Hz).
"""

import cv2
import numpy as np

WIDTH, HEIGHT = 640, 352           # 모델 입력 = 컬러 preview 크기
DEPTH_WIDTH, DEPTH_HEIGHT = 640, 360
# 깊이는 ISP 화면(640x360) 전체에 정렬돼 나오므로 preview와 같은 영역만 남기려면 위에서 이만큼 자른다
DEPTH_ROW_OFFSET = (DEPTH_HEIGHT - HEIGHT) // 2
FPS = 20
CLASS_NAMES = {0: 'person', 1: 'leg'}


def build_pipeline(with_depth=True, blob_path=None, threads=2):
    """컬러(+깊이)(+NN) 파이프라인. 출력 스트림 이름: 'rgb', 'depth', 'nn' (만든 것만)."""
    import depthai as dai

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
        _xout(p, 'rgb', nn.passthrough)   # NN에 들어간 바로 그 프레임 (nn 출력과 sequence 번호가 같다)
        _xout(p, 'nn', nn.out)
    else:
        _xout(p, 'rgb', cam.preview)
    return p


def _xout(pipeline, name, source):
    import depthai as dai

    x = pipeline.create(dai.node.XLinkOut)
    x.setStreamName(name)
    source.link(x.input)


def decode(nn_data, conf=0.3, iou=0.5):
    """NN 출력(depthai NNData) → [x1, y1, x2, y2, 점수, 클래스] 배열 (픽셀 단위, NMS 뒤). 없으면 (0, 6)."""
    return decode_output(nn_data.getLayerFp16('output0'), conf, iou)


def decode_output(raw, conf=0.3, iou=0.5):
    """모델 원시 출력(6 × 후보 수로 펼친 값) → [x1, y1, x2, y2, 점수, 클래스] 배열. 없으면 (0, 6)."""
    raw = np.asarray(raw, dtype=np.float32).reshape(6, -1)
    boxes, scores = raw[:4].T, raw[4:].T
    cls = scores.argmax(1)
    best = scores.max(1)
    keep = best > conf
    boxes, best, cls = boxes[keep], best[keep], cls[keep]
    if len(best) == 0:
        return np.zeros((0, 6))
    xywh = np.column_stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2,
                            boxes[:, 2], boxes[:, 3]])
    idx = np.array(cv2.dnn.NMSBoxes(xywh.tolist(), best.tolist(), conf, iou)).reshape(-1)
    xyxy = np.column_stack([xywh[:, :2], xywh[:, :2] + xywh[:, 2:]])
    return np.column_stack([xyxy[idx], best[idx], cls[idx]])


def crop_depth(depth):
    """컬러 preview(640x352)와 같은 영역의 깊이만 남긴다."""
    return depth[DEPTH_ROW_OFFSET:DEPTH_ROW_OFFSET + HEIGHT]


def preview_intrinsics(calib):
    """장치 보정값에서 preview(640x352) 기준 K 행렬(3x3 목록)과 왜곡 계수를 얻는다."""
    import depthai as dai

    k = np.array(calib.getCameraIntrinsics(dai.CameraBoardSocket.CAM_A, DEPTH_WIDTH, DEPTH_HEIGHT))
    k[1, 2] -= DEPTH_ROW_OFFSET   # preview는 ISP 화면 위를 잘랐으므로 cy만 옮긴다
    distortion = list(calib.getDistortionCoefficients(dai.CameraBoardSocket.CAM_A))
    return k, distortion


class FrameMatcher:
    """
    NN 결과·그 입력 프레임·깊이를 한 묶음으로 짝짓는다.

    NN 결과와 passthrough 프레임은 sequence 번호가 같다. 깊이는 모노 카메라에서 따로 나오므로
    장치 시각이 가장 가까운 것을 고른다. 컬러와 모노는 노출 시각이 하드웨어로 맞춰지지 않는다.
    """

    def __init__(self, max_depth_gap=1.0 / FPS, keep=8):
        self.max_depth_gap = max_depth_gap  # sec
        self.keep = keep
        self.frames = {}   # seq → (t, frame)
        self.results = {}  # seq → nn 결과
        self.depths = []   # (t, depth), 오래된 것부터

    def add_frame(self, seq, t, frame):
        self.frames[seq] = (t, frame)
        return self._pop(seq)

    def add_result(self, seq, result):
        self.results[seq] = result
        return self._pop(seq)

    def add_depth(self, t, depth):
        self.depths.append((t, depth))
        del self.depths[:-self.keep]

    def _pop(self, seq):
        """seq의 프레임과 결과가 다 모였으면 (t, frame, result, depth 또는 None)을 돌려준다."""
        if seq not in self.frames or seq not in self.results:
            self._prune(seq)
            return None
        t, frame = self.frames.pop(seq)
        result = self.results.pop(seq)
        self._prune(seq)
        depth = None
        if self.depths:
            td, depth_frame = min(self.depths, key=lambda item: abs(item[0] - t))
            if abs(td - t) <= self.max_depth_gap:
                depth = depth_frame
        return t, frame, result, depth

    def _prune(self, seq):
        # 짝이 끝내 안 온 것(NN이 프레임을 버렸을 때)이 쌓이지 않게 오래된 번호를 지운다
        for table in (self.frames, self.results):
            for old in [s for s in table if s < seq - self.keep]:
                del table[old]


class ReconnectBackoff:
    """다시 연결할 때까지 기다릴 시간. 실패할수록 두 배로 늘리고(최대 max_delay), 영상을 받으면 처음으로 돌린다."""

    def __init__(self, min_delay=1.0, max_delay=10.0):
        self.min_delay = min_delay  # sec
        self.max_delay = max_delay  # sec
        self.delay = min_delay

    def next_delay(self):
        delay = self.delay
        self.delay = min(self.delay * 2.0, self.max_delay)
        return delay

    def reset(self):
        self.delay = self.min_delay
