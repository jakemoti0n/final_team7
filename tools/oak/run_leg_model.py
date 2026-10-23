#!/usr/bin/env python3
"""하반신 모델(leg_640 blob)을 OAK-D Lite 안에서 돌려 본다. 실물 배치 구성(컬러 + 정렬 깊이 + NN).

실행:
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/run_leg_model.py                 # 10초 돌고 마지막 프레임을 oak_last.png로 저장
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/run_leg_model.py --no-depth      # NN만 (카메라 한계 19.7 Hz까지 나오는지)
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/run_leg_model.py --blob 다른.blob --threads 1
사람이 카메라 앞 1.5~3 m에 서면 1초마다 검출 결과가 찍힌다. 기대값(노트북 USB 2.0, 2026-10-23): 깊이 있을 때 NN 14.5~14.8 Hz·지연 ~230 ms, --no-depth면 17 Hz(3 shave 블롭 기준. NN만 쓸 거면 8 shave로 다시 변환하면 카메라 한계 19.7 Hz).
"""
import argparse
import time

import cv2
import depthai as dai
import numpy as np

import oak_common as oc

parser = oc.add_common_args(argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter))
parser.add_argument('--blob', default=oc.DEFAULT_BLOB)
parser.add_argument('--threads', type=int, default=2, help='NN 추론 스레드. 3 shave 블롭은 2')
parser.add_argument('--no-depth', action='store_true', help='스테레오 깊이 없이 NN만')
parser.add_argument('--conf', type=float, default=0.3, help='검출 문턱(person_detector.yaml의 conf와 같게)')
parser.add_argument('--save', default='oak_last.png', help='마지막 프레임 저장 파일')
args = parser.parse_args()

pipeline = oc.build_pipeline(with_depth=not args.no_depth, blob_path=args.blob, threads=args.threads)
with dai.Device(pipeline, oc.usb_speed(args.usb)) as dev:
    print(f'이름 {dev.getDeviceName()} | USB {dev.getUsbSpeed().name} | blob {args.blob}')
    names = ['rgb', 'nn'] + ([] if args.no_depth else ['depth'])
    q = {n: dev.getOutputQueue(n, 4, False) for n in names}
    count = {n: 0 for n in names}
    lat, last = [], None
    t0 = time.time(); t_print = t0
    while time.time() - t0 < args.seconds:
        if q['rgb'].has():
            last = q['rgb'].get().getCvFrame(); count['rgb'] += 1
        if q['nn'].has():
            nn = q['nn'].get(); count['nn'] += 1
            dets = oc.decode(nn, args.conf); lat.append(oc.latency_ms(nn))
            if time.time() - t_print >= 1:
                t_print = time.time()
                print(f'{t_print - t0:4.0f}s 검출 {len(dets)}개', [(oc.CLASS_NAMES[int(c)], round(float(s), 2)) for *_, s, c in dets])
                if last is not None:
                    last_drawn = oc.draw(last.copy(), dets)
        if 'depth' in q and q['depth'].has():
            q['depth'].get(); count['depth'] += 1
        time.sleep(0.002)
    s = args.seconds
    print(f'{s:.0f}초: ' + ', '.join(f'{n} {c/s:.1f} Hz' for n, c in count.items()) +
          f' | NN 지연 중앙값 {np.median(lat):.0f} ms | 칩 CPU {dev.getLeonCssCpuUsage().average*100:.0f}%/{dev.getLeonMssCpuUsage().average*100:.0f}% | 온도 {dev.getChipTemperature().average:.0f}°C')
    if last is not None:
        cv2.imwrite(args.save, locals().get('last_drawn', last)); print('저장:', args.save)
