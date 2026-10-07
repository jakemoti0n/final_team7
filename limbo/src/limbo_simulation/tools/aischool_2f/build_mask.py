"""도면 사진(floorplan_photo.png)을 펴고 벽 마스크(walls.png)를 만든다. 수동 보정은 아래 목록에서만 한다.

사용법: python3 build_mask.py && python3 gen_world.py
"""
import cv2, numpy as np

# 사진에서 건물 바깥 벽 네 모서리 (왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래) — 원근 보정용
PHOTO_CORNERS = [(49, 48), (845, 63), (826, 773), (88, 804)]

# 방 이름표·기호 상자 (x0, y0, x1, y1) — 벽이 아니라 지운다
LABELS = [(93,82,193,103),(637,84,740,105),(138,263,243,286),(555,262,628,287),(47,358,152,380),
          (333,293,437,314),(622,358,727,380),(356,449,460,470),(346,575,450,596),(93,623,195,645),
          (512,635,614,657),(643,624,745,646),(220,372,248,392),
          (716,198,742,224),(452,226,472,248),(293,423,315,447),(527,268,552,292)]  # 비상구·비상벨 기호
# 계단실·엘리베이터·창고 코어 — 로봇이 못 들어가므로 막는다
SOLID = [(248,245,522,422)]
# 문 — 벽을 뚫어 통로로 만든다 (보정 단계에서 채움)
DOORS = [
    (259,184,289,202),(283,196,292,222),   # 207 교실-6 문 + 문짝
    (482,184,510,202),(478,194,490,226),   # 206 교실-5 문 / 복도 방화문 문짝
    (244,533,272,553),(243,515,252,550),   # 202 교실-1
    (352,533,380,553),(350,515,359,572),   # 209 상담실
    (494,533,522,553),(514,515,524,552),   # 203 휴게실
    (717,533,745,553),(715,515,725,552),   # 204 교실-3
]
WALL_THICKNESS = 5

photo=cv2.imread('floorplan_photo.png')
src=np.float32(PHOTO_CORNERS)
W=int(round((np.linalg.norm(src[1]-src[0])+np.linalg.norm(src[2]-src[3]))/2))
H=int(round((np.linalg.norm(src[3]-src[0])+np.linalg.norm(src[2]-src[1]))/2))
r=cv2.warpPerspective(photo,cv2.getPerspectiveTransform(src,np.float32([[0,0],[W,0],[W,H],[0,H]])),(W,H),borderValue=(255,255,255))
cv2.imwrite('rectified.png',r)
g=cv2.cvtColor(r,cv2.COLOR_BGR2GRAY); hsv=cv2.cvtColor(r,cv2.COLOR_BGR2HSV)
dark=cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,31,18)
b,gg,rr=[r[...,i].astype(int) for i in range(3)]
pink=((rr-gg>35)&(rr-b>25)).astype(np.uint8)*255
dark[cv2.dilate(pink,np.ones((5,5),np.uint8))>0]=0
dark[cv2.dilate((hsv[...,1]>70).astype(np.uint8)*255,np.ones((5,5),np.uint8))>0]=0
L=22
h=cv2.morphologyEx(dark,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(L,1)))
v=cv2.morphologyEx(dark,cv2.MORPH_OPEN,cv2.getStructuringElement(cv2.MORPH_RECT,(1,L)))
walls=cv2.bitwise_or(h,v)
for x0,y0,x1,y1 in LABELS: walls[y0-2:y1+3,x0-2:x1+3]=0
walls=cv2.dilate(walls,np.ones((WALL_THICKNESS,WALL_THICKNESS),np.uint8))
for x0,y0,x1,y1 in SOLID: walls[y0:y1,x0:x1]=255
for x0,y0,x1,y1 in DOORS: walls[y0:y1,x0:x1]=0
H,W=walls.shape; walls[:3,:]=walls[-3:,:]=255; walls[:,:3]=walls[:,-3:]=255
cv2.imwrite('walls.png',walls)

# 홀(201)에서 갈 수 있는 곳 표시: 로봇 반경만큼 벽을 부풀린 뒤 flood fill
ROBOT_RADIUS_PX = 8
inflated=cv2.dilate(walls,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*ROBOT_RADIUS_PX+1,)*2))
free=(inflated==0).astype(np.uint8)
n,lab=cv2.connectedComponents(free)
reach=(lab==lab[500,400]).astype(np.uint8)
vis=r.copy(); vis[walls>0]=(0,0,0)
vis[(reach>0)&(walls==0)]=(vis[(reach>0)&(walls==0)]*0.4+np.array([80,200,80])*0.6).astype(np.uint8)
cv2.imwrite('reach.png',vis)
