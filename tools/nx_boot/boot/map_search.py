"""Stationary scan-to-map search. Candidate coordinates are in grid cells and radians."""
import math

import cv2
import numpy as np


def separate(a, b, resolution):
    delta = math.remainder(a[2] - b[2], 2 * math.pi)
    return math.hypot(a[0]-b[0], a[1]-b[1])*resolution > .45 or abs(delta) > math.radians(12)


class MapSearch:
    def __init__(self, grid, resolution):
        self.res = resolution
        self.free = (grid >= 0) & (grid < 35)
        occupied = (grid >= 65).astype(np.uint8)
        self.fine = cv2.dilate(occupied, np.ones((5, 5), np.uint8))
        distance = cv2.distanceTransform(1-occupied, cv2.DIST_L2, 5) * resolution
        self.soft = np.exp(-.5*(distance/.19)**2).astype(np.float32)
        self.distance = distance
        self.step = max(1, round(.15/resolution))
        rows, cols = np.where(self.free[::self.step, ::self.step])
        self.x = cols.astype(np.int32)*self.step
        self.y = rows.astype(np.int32)*self.step

    def scores(self, x, y, heading, points, field):
        c, s = math.cos(heading), math.sin(heading)
        dx = np.floor(.5+(c*points[0]-s*points[1])/self.res).astype(np.int32)
        dy = np.floor(.5+(s*points[0]+c*points[1])/self.res).astype(np.int32)
        ix = x[:, None]+dx
        iy = y[:, None]+dy
        inside = (ix>=0)&(iy>=0)&(ix<field.shape[1])&(iy<field.shape[0])
        return (field[iy.clip(0,field.shape[0]-1),ix.clip(0,field.shape[1]-1)]*inside).mean(axis=1)

    def locate(self, points):
        if len(self.x)==0:
            return None
        sample = points[:,np.linspace(0,points.shape[1]-1,min(80,points.shape[1]),dtype=int)]
        seeds=[]
        for degrees in range(-180,180,5):
            angle=math.radians(degrees)
            values=self.scores(self.x,self.y,angle,sample,self.soft)
            # Preserve spatially distinct matches at every orientation.
            for _ in range(8):
                i=int(np.argmax(values))
                score=float(values[i])
                if score < .50:break
                x,y=self.x[i],self.y[i]
                seeds.append((score,int(x),int(y),angle))
                values[(self.x-x)**2+(self.y-y)**2<=(.38/self.res)**2]=-1
                if _==7 and values.max()>=.78:
                    return None
        if not seeds:return None
        peaks=[]
        for val,x,y,h in sorted(seeds,reverse=True):
            if val < max(.50,max(v[0] for v in seeds)-.22):break
            if any(not separate((x,y,h),p,self.res) for p in peaks):continue
            peaks.append((x,y,h))
        if len(peaks)>50:return None
        results=[]
        for x,y,h in peaks:
            half=max(self.step,math.ceil(.22/self.res))
            yy,xx=np.mgrid[max(0,y-half):min(self.free.shape[0],y+half+1),max(0,x-half):min(self.free.shape[1],x+half+1)]
            valid=self.free[yy,xx];xx=xx[valid];yy=yy[valid]
            best=(-1,None)
            for delta in range(-5,6):
                angle=h+math.radians(delta)
                fit=self.scores(xx,yy,angle,points,self.fine)
                quality=self.scores(xx,yy,angle,points,self.soft)
                rank=.8*fit+.2*quality
                i=int(np.argmax(rank))
                if rank[i]>best[0]:
                    best=(float(rank[i]),(int(xx[i]),int(yy[i]),angle,float(fit[i])))
            results.append(best)
        results.sort(reverse=True)
        score,p=results[0]
        runner=max((s for s,q in results[1:] if separate(q,p,self.res)),default=0.)
        if p[3]<.85 or score-runner<.08:
            return None
        return p,runner
