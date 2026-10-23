#!/usr/bin/env python3
"""하반신 모델(.pt) → ONNX → OAK blob. 모델을 다시 학습했을 때만 쓴다. 두 단계는 서로 다른 venv에서 돈다.

1단계 ONNX (ultralytics가 있는 limbo_yolo venv):
  ~/limbo/venvs/limbo_yolo/bin/python tools/oak/export_blob.py onnx limbo/src/limbo_perception/models/leg_640.pt
  주의: ultralytics가 onnx를 깔면서 numpy를 2.x로 올려 버린다. 끝나면 되돌린다:
  ~/limbo/venvs/limbo_yolo/bin/pip install numpy==1.26.4 && ~/limbo/venvs/limbo_yolo/bin/pip uninstall -y onnx onnxruntime onnxslim ml_dtypes flatbuffers protobuf
2단계 blob (limbo_oak venv, 인터넷 필요 — Luxonis 변환 서버에 ONNX를 보낸다):
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/export_blob.py blob leg_640.onnx --shaves 3
입력은 640x352(16:9). 색 순서 뒤집기(BGR→RGB)와 /255 정규화를 blob 안에 넣어 호스트는 preview 프레임을 그대로 넣으면 된다.
"""
import argparse
import sys

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('step', choices=['onnx', 'blob'])
parser.add_argument('model', help='onnx 단계: .pt 파일, blob 단계: .onnx 파일')
parser.add_argument('--shaves', type=int, default=3, help='스테레오와 같이 쓰면 3(2 thread). NN만 쓰면 8')
parser.add_argument('--out', default='.', help='blob을 저장할 폴더')
args = parser.parse_args()

if args.step == 'onnx':
    from ultralytics import YOLO
    model = YOLO(args.model)
    print('클래스:', model.names)
    print('저장:', model.export(format='onnx', imgsz=[352, 640], opset=12, simplify=True, dynamic=False, half=False))
else:
    import blobconverter
    path = blobconverter.from_onnx(model=args.model, data_type='FP16', shaves=args.shaves, version='2022.1',
                                   optimizer_params=['--reverse_input_channels', '--scale_values=[255,255,255]'],
                                   output_dir=args.out)
    print('저장:', path, file=sys.stderr)
