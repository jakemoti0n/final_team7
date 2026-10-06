#!/usr/bin/env python3
"""A-2 검증셋 오염→clean 오류/정답 사례 추출. 원본·라벨·체크포인트 읽기 전용.

서버: python -u audit_model_a_errors.py --out /data/recycle_dataset/notebooks/model\ A/audit_A2_v1
출력: cases.csv(수동 검수 칸 포함), previews/, samples.zip. 실제 오류 원인은 사람의 사진 검수가 필요.
의존성: ultralytics, pillow, pyyaml (A-2 학습 환경과 동일).
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

NAMES = ['paper_clean','paper_contaminated','can_clean','can_contaminated',
         'pet_clean','pet_contaminated','glass_clean','glass_contaminated',
         'plastic_clean','plastic_contaminated','vinyl_clean','vinyl_contaminated',
         'styrofoam_clean','styrofoam_contaminated']
EXT = {'.jpg','.jpeg','.png','.bmp','.webp'}

def iou(a, b):
    x1,y1,x2,y2 = a; X1,Y1,X2,Y2 = b
    inter = max(0,min(x2,X2)-max(x1,X1))*max(0,min(y2,Y2)-max(y1,Y1))
    aa=max(0,x2-x1)*max(0,y2-y1); bb=max(0,X2-X1)*max(0,Y2-Y1)
    return inter/(aa+bb-inter) if aa+bb-inter else 0.0

def match_boxes(gt, pred, threshold=.45):
    # Ultralytics 혼동행렬과 같은 종류의 class-agnostic IoU 우선 1:1 매칭 후보.
    pairs=sorted(((iou(g[1],p[2]),gi,pi) for gi,g in enumerate(gt)
                  for pi,p in enumerate(pred)), reverse=True)
    matched={}; used=set()
    for overlap,gi,pi in pairs:
        if overlap <= threshold: break
        if gi not in matched and pi not in used:
            matched[gi]=pi; used.add(pi)
    return matched

def classify_match(true_id, pred_id):
    if pred_id is None: return 'missed'
    if pred_id == true_id: return 'correct_dirty'
    if pred_id % 2 == 0:
        return 'same_material_clean' if pred_id == true_id-1 else 'other_material_clean'
    return 'other_dirty'

def group_key(path):
    stem=Path(path).stem.split('.rf.')[0]
    return re.sub(r'_\d+_(?:jpg|jpeg|png)$','',stem,flags=re.I)

def choose_cases(cases, limit):
    cases=sorted(cases,key=lambda c: hashlib.sha256(str(c['image_path']).encode()).hexdigest())
    selected=[]; groups=set()
    for c in cases:
        if c['source_group'] not in groups:
            selected.append(c);groups.add(c['source_group'])
            if len(selected)>=limit: return selected
    for c in cases:
        if c not in selected:
            selected.append(c)
            if len(selected)>=limit: break
    return selected

def read_gt(path, w, h):
    boxes=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip(): continue
        c,x,y,bw,bh=map(float,line.split())
        if c != int(c) or not 0<=c<14: raise ValueError(f'{path}: class ID invalid')
        if not all(0<=v<=1 for v in (x,y,bw,bh)): raise ValueError(f'{path}: bbox invalid')
        boxes.append((int(c), ((x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h)))
    return boxes

def render(case, dest):
    from PIL import Image, ImageDraw, ImageOps
    with Image.open(case['image_path']) as raw: image=raw.convert('RGB')
    d=ImageDraw.Draw(image)
    g=case['gt_box']; p=case['pred_box']
    d.rectangle(g,outline='yellow',width=max(3,image.width//300))
    d.text((max(0,g[0]),max(0,g[1]-15)),f"GT {case['true_class']}",fill='yellow',stroke_width=2,stroke_fill='black')
    if p:
        d.rectangle(p,outline='red' if 'clean' in case['outcome'] else 'cyan',width=max(3,image.width//300))
        d.text((max(0,p[0]),min(image.height-16,p[3]+2)),f"PRED {case['pred_class']} {case['confidence']:.2f}",fill='red',stroke_width=2,stroke_fill='black')
    left=ImageOps.contain(image,(700,520))
    crop=image.crop((max(0,int(g[0]-(g[2]-g[0])*.25)),max(0,int(g[1]-(g[3]-g[1])*.25)),
                     min(image.width,int(g[2]+(g[2]-g[0])*.25)),min(image.height,int(g[3]+(g[3]-g[1])*.25))))
    right=ImageOps.contain(crop,(520,520))
    canvas=Image.new('RGB',(1240,550),'#202020')
    canvas.paste(left,(10,25));canvas.paste(right,(710,25))
    ImageDraw.Draw(canvas).text((10,5),f"{case['outcome']}  {case['true_class']} -> {case['pred_class']}",fill='white')
    canvas.save(dest,quality=88)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=Path('/data/recycle_dataset/model_a_stage1_14class_27500_v1/data.yaml'))
    p.add_argument('--weights',type=Path,default=Path('/data/recycle_dataset/notebooks/model A/runs/recycle_yolo11n_14class_A-2/weights/best.pt'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--limit',type=int,default=8,help='클래스·상태별 미리보기 상한')
    a=p.parse_args()
    if a.out.exists(): raise FileExistsError(f'검수 결과 덮어쓰기 금지: {a.out}')
    if not a.data.is_file() or not a.weights.is_file(): raise FileNotFoundError('data.yaml 또는 best.pt 없음')
    import yaml
    from ultralytics import YOLO
    cfg=yaml.safe_load(a.data.read_text(encoding='utf-8-sig'))
    names=cfg['names']; names=[names[i] if isinstance(names,list) else names.get(i,names.get(str(i))) for i in range(14)]
    if names != NAMES: raise ValueError(f'클래스 ID/순서 불일치: {names}')
    root=Path(cfg.get('path') or a.data.parent)
    if not root.is_absolute(): root=(a.data.parent/root).resolve()
    val=Path(cfg['val']); val=val if val.is_absolute() else root/val
    labeldir=root/'labels'/'val'
    images=sorted(f for f in val.iterdir() if f.is_file() and f.suffix.lower() in EXT)
    if not images: raise ValueError(f'val 이미지 없음: {val}')
    if any(not (labeldir/(f.stem+'.txt')).is_file() for f in images): raise ValueError('이미지-라벨 누락')
    print(f'검수 후보 검색: {len(images)} val 이미지, A-2 best.pt, conf=0.25 IoU match=0.45',flush=True)
    model=YOLO(str(a.weights))
    if [model.names[i] for i in range(14)] != NAMES: raise ValueError('체크포인트 class 순서 불일치')
    candidates=[]; observed=Counter()
    for index,result in enumerate(model.predict(source=str(val), stream=True, batch=8,
                     imgsz=640,conf=.25,iou=.7,agnostic_nms=False,device=0,verbose=False),1):
        img=Path(result.path); h,w=result.orig_shape
        gt=read_gt(labeldir/(img.stem+'.txt'),w,h)
        xyxy=result.boxes.xyxy.cpu().tolist(); cls=result.boxes.cls.cpu().tolist(); conf=result.boxes.conf.cpu().tolist()
        pred=[(int(c),float(score),tuple(box)) for c,score,box in zip(cls,conf,xyxy)]
        matches=match_boxes(gt,pred)
        for gi,(tc,gbox) in enumerate(gt):
            if tc%2==0:continue
            pi=matches.get(gi); pc=pred[pi][0] if pi is not None else None
            outcome=classify_match(tc,pc)
            observed[(tc,outcome)]+=1
            candidates.append(dict(image_path=str(img),source_group=group_key(img),true_class=NAMES[tc],
                pred_class=NAMES[pc] if pc is not None else 'background',outcome=outcome,
                confidence=pred[pi][1] if pi is not None else 0,gt_box=gbox,
                pred_box=pred[pi][2] if pi is not None else None,gt_index=gi))
        if index%300==0:print('processed',index,flush=True)
    buckets=defaultdict(list)
    for c in candidates:
        tc=NAMES.index(c['true_class'])
        kind='error' if c['outcome'] in {'same_material_clean','other_material_clean'} else c['outcome']
        buckets[(tc,kind)].append(c)
    selected=[]
    for (tc,kind),cases in sorted(buckets.items()):
        if kind not in {'error','correct_dirty'}:continue
        selected.extend(choose_cases(cases,a.limit))
    a.out.mkdir(parents=True); previews=a.out/'previews';previews.mkdir()
    fields=['preview','image_path','source_group','true_class','pred_class','outcome','confidence',
            'contamination_visible','label_consistent','background_shortcut_suspected','failure_type','notes']
    with (a.out/'cases.csv').open('w',newline='',encoding='utf-8-sig') as file:
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for i,c in enumerate(selected,1):
            name=f"{i:03d}_{c['true_class']}_{c['outcome']}.jpg"
            render(c,previews/name)
            row={k:c.get(k,'') for k in fields};row['preview']=f'previews/{name}'
            writer.writerow(row)
    with (a.out/'summary.txt').open('w',encoding='utf-8') as file:
        file.write('A-2 후보 검색. 자체 IoU 매칭으로 얻은 검수 후보이며 Ultralytics 혼동행렬 정확 재현이 아님.\n')
        file.write('오염 가시성/라벨 일관성/촬영 지름길은 자동 판정하지 않았음. cases.csv에 수동 기록.\n')
        file.write('원본은 읽기 전용, 출력 이미지에만 오버레이. conf=0.25, IoU=0.45.\n')
        for (tc,outcome),n in sorted(observed.items()):file.write(f'{NAMES[tc]} {outcome}: {n}\n')
    archive=a.out/'samples.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for path in [a.out/'cases.csv',a.out/'summary.txt',*previews.glob('*.jpg')]:z.write(path,path.relative_to(a.out))
    print(f'완료: {len(selected)}개 검수 미리보기, {archive}',flush=True)

if __name__=='__main__':main()
