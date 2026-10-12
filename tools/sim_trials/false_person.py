"""사람(actor)이 없는 위치에 나온 person 박스를 센다. 사용법: false_person.py <frames.npz> <모델.pt> ..."""
import os
import math, sys, numpy as np
from limbo_evaluation import actors
from ultralytics import YOLO
TRAJ = actors.parse_actor_trajectories(open(os.path.expanduser('~/limbo/limbo/src/limbo_simulation/worlds/aischool_2f_scenarios.sdf')).read())
FX = 160 / math.tan(1.25 / 2); CAM = 0.22
data = np.load(sys.argv[1])
for path in sys.argv[2:]:
    model = YOLO(path); false = []; total = 0
    for frame, t in zip(data['frames'], data['stamps']):
        us = []
        for tr in TRAJ.values():
            x, y = actors.position_at(tr, float(t)); b = math.atan2(y, x - CAM)
            if abs(b) < 0.7 and x > CAM: us.append(160 - FX * math.tan(b))
        r = model.predict(frame[:, :, ::-1].copy(), conf=0.3, verbose=False)[0]
        for cls, conf, (x1, y1, x2, y2) in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist()):
            if r.names[int(cls)] != 'person': continue
            total += 1
            if all(abs((x1 + x2) / 2 - u) > 60 for u in us): false.append((round(float(t), 1), round(conf, 2), [int(v) for v in (x1, y1, x2, y2)]))
    print(f'{path.split("/")[-1]:10s} person 박스 {total}개 중 사람 없는 위치 {len(false)}개', false[:5])
