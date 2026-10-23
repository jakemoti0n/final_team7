#!/usr/bin/env python3
"""OAK-D Lite가 제대로 붙었는지 확인한다. 모델 없이 컬러·깊이만.

처음 한 번(sudo):
  echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
  sudo udevadm control --reload-rules && sudo udevadm trigger   # 그래도 안 되면 카메라를 뽑았다 다시 꽂는다
실행:
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/check_camera.py            # USB 2.0 케이블(기본)
  ~/limbo/venvs/limbo_oak/bin/python tools/oak/check_camera.py --usb super # USB 3 케이블
기대값(노트북 USB 2.0, 2026-10-23): rgb·depth 19.7 Hz, 깊이 지연 ~80 ms, 깊이 유효 비율 0.5~0.99(장면에 따라), 칩 온도 40°C대.
"""
import argparse
import time

import depthai as dai
import numpy as np

import oak_common as oc

parser = oc.add_common_args(argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter))
args = parser.parse_args()

found = dai.Device.getAllAvailableDevices()
print('보이는 장치:', [(d.getMxId(), d.state.name) for d in found])
if not found:
    raise SystemExit('OAK를 못 찾음. lsusb에 03e7이 있는지, udev 규칙(위 설명)을 넣었는지 확인')

with dai.Device(oc.build_pipeline(with_depth=True), oc.usb_speed(args.usb)) as dev:
    print(f'이름 {dev.getDeviceName()} | USB {dev.getUsbSpeed().name} | MXID {dev.getMxId()}')
    for f in dev.getConnectedCameraFeatures():
        print(f'  {f.socket.name}: {f.sensorName} {f.width}x{f.height}')
    q_rgb, q_depth = dev.getOutputQueue('rgb', 4, False), dev.getOutputQueue('depth', 4, False)
    count = {'rgb': 0, 'depth': 0}
    lat, valid, center = [], [], []
    t0 = time.time()
    while time.time() - t0 < args.seconds:
        if q_rgb.has():
            q_rgb.get(); count['rgb'] += 1
        if q_depth.has():
            d = q_depth.get(); count['depth'] += 1
            frame = d.getFrame()
            lat.append(oc.latency_ms(d)); valid.append((frame > 0).mean())
            center.append(frame[frame.shape[0] // 2, frame.shape[1] // 2])
        time.sleep(0.002)
    s = args.seconds
    print(f'{s:.0f}초: rgb {count["rgb"]/s:.1f} Hz, depth {count["depth"]/s:.1f} Hz | 깊이 지연 중앙값 {np.median(lat):.0f} ms | '
          f'깊이 유효 비율 {np.mean(valid):.2f} | 가운데 깊이 {np.median(center):.0f} mm | '
          f'칩 CPU {dev.getLeonCssCpuUsage().average*100:.0f}%/{dev.getLeonMssCpuUsage().average*100:.0f}% | 온도 {dev.getChipTemperature().average:.0f}°C')
