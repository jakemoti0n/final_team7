"""Initialize AMCL from a stationary global scan match and checkpoint validated poses."""
import hashlib
import json
import math
import os
from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from map_search import MapSearch
from action_msgs.msg import GoalStatus, GoalStatusArray
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import OccupancyGrid, Odometry
from sensor_msgs.msg import LaserScan
from rclpy.qos import QoSProfile, DurabilityPolicy, qos_profile_sensor_data
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener, TransformException

FILE = Path.home()/'.local/state/limbo/corridor-pose.json'
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))

def write(data):
    FILE.parent.mkdir(parents=True,exist_ok=True)
    tmp = FILE.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(FILE)

def scan_fit(pose,bx,by,g,walls):
    x,y,h=pose
    wx=x+math.cos(h)*bx-math.sin(h)*by-g.origin.position.x
    wy=y+math.sin(h)*bx+math.cos(h)*by-g.origin.position.y
    gh=yaw(g.origin.orientation)
    ix=np.floor((math.cos(gh)*wx+math.sin(gh)*wy)/g.resolution).astype(int)
    iy=np.floor((-math.sin(gh)*wx+math.cos(gh)*wy)/g.resolution).astype(int)
    ok=(ix>=0)&(ix<g.width)&(iy>=0)&(iy<g.height)
    return float(walls[iy[ok],ix[ok]].sum()/len(ix))


def moving(twist):
    return math.hypot(twist.linear.x,twist.linear.y)>.005 or abs(twist.angular.z)>.01


def main():
    rclpy.init()
    n = rclpy.create_node('limbo_corridor_pose')
    buf = Buffer()
    listener = TransformListener(buf,n)
    latest = {}
    def remember(key):
        return lambda m: latest.update({key:(m,time.monotonic())})
    for key, typ, topic, qos in [('map',OccupancyGrid,'/map',LATCHED),
             ('scan',LaserScan,'/scan',qos_profile_sensor_data),
             ('odom',Odometry,'/odom',qos_profile_sensor_data)]:
        n.create_subscription(typ,topic,remember(key),qos)
    active_goals={}
    last_motion=time.monotonic()
    def status_for(action):
        def update(msg):
            active_goals[action]=any(goal.status in (GoalStatus.STATUS_ACCEPTED,
                GoalStatus.STATUS_EXECUTING, GoalStatus.STATUS_CANCELING) for goal in msg.status_list)
        return update
    def track_motion(msg):
        nonlocal last_motion
        if moving(msg):
            last_motion=time.monotonic()
    n.create_subscription(Twist,'/cmd_vel',track_motion,qos_profile_sensor_data)
    for action in ('navigate_to_pose','navigate_through_poses','follow_path'):
        n.create_subscription(GoalStatusArray,'/'+action+'/_action/status',status_for(action),LATCHED)
    poor_scans=0
    previous_check=0.
    pub = n.create_publisher(PoseWithCovarianceStamped,'/initialpose',10)
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    last_map = None
    checked = 0
    last_write = 0
    matches = 0
    candidate = None
    retry_after = 0.0
    sent_at = -100.0
    last_scan = None
    while rclpy.ok():
        rclpy.spin_once(n,timeout_sec=.2)
        now=time.monotonic()
        if now-checked < .45 or not {'map','scan','odom'} <= latest.keys():continue
        checked=now
        grid,version=latest['map']
        if version!=last_map:
            g=grid.info
            a=np.frombuffer(grid.data,dtype=np.int8).reshape(g.height,g.width)
            walls=cv2.dilate((a>=65).astype(np.uint8),np.ones((5,5),np.uint8))
            signature=hashlib.sha256(a.tobytes()+repr((g.width,g.height,g.resolution,g.origin)).encode()).hexdigest()
            poor_scans=0
            search=MapSearch(a,g.resolution)
            candidate=None
            retry_after=0.0
            last_map=version
            matches=0
        scan,ts=latest['scan']
        stamp=(scan.header.stamp.sec,scan.header.stamp.nanosec)
        if stamp==last_scan:continue
        last_scan=stamp
        odom,to=latest['odom']
        ros_now=n.get_clock().now().nanoseconds/1e9
        scan_time=stamp[0]+stamp[1]*1e-9
        odom_time=odom.header.stamp.sec+odom.header.stamp.nanosec*1e-9
        if max(now-ts,now-to)>.6 or not all(-.2<=ros_now-t<=.65 for t in (scan_time,odom_time)):
            matches=0
            continue
        try:
            mount=buf.lookup_transform('base_footprint',scan.header.frame_id,Time()).transform
        except TransformException:continue
        try:
            stamped=buf.lookup_transform('map','base_footprint',Time())
            age=(n.get_clock().now().nanoseconds-Time.from_msg(stamped.header.stamp).nanoseconds)/1e9
            if not -1.5<=age<=.7:continue
            tr=stamped.transform
            pose=[tr.translation.x,tr.translation.y,yaw(tr.rotation)]
            localized=True
        except TransformException:
            localized=False
        ranges=np.asarray(scan.ranges)
        good=np.isfinite(ranges)&(ranges>scan.range_min)&(ranges<min(8.,scan.range_max))
        if good.sum()<70:matches=0;continue
        angles=scan.angle_min+np.flatnonzero(good)*scan.angle_increment+yaw(mount.rotation)
        bx=mount.translation.x+ranges[good]*np.cos(angles)
        by=mount.translation.y+ranges[good]*np.sin(angles)
        continuous=now-previous_check<=1.5
        previous_check=now
        if not continuous:
            poor_scans=0
            matches=0
            candidate=None
        if localized:
            current_fit=scan_fit(pose,bx,by,g,walls)
            if current_fit>=.80:
                candidate=None
                poor_scans=matches=0
                if now-last_write>=1:
                    write({'boot':boot,'map':signature,'pose':pose,'fit':round(current_fit,3),'time':time.time()})
                    last_write=now
                continue
        if moving(odom.twist.twist):
            last_motion=now
        if now-last_motion<3 or n.count_publishers('/patrol/state') or any(active_goals.values()):
            poor_scans=matches=0
            candidate=None
            continue
        if localized:
            poor_scans+=1
            if poor_scans<6:continue
        if now-sent_at<10:continue
        if candidate is None:
            if now<retry_after:continue

            result=search.locate(np.asarray([bx,by]))
            previous_check=time.monotonic()
            retry_after=previous_check+3
            if result is None:
                print('No unique global scan match; waiting for another scan',flush=True)
                continue
            (cx,cy,ch,fit),runner=result
            gh=yaw(g.origin.orientation)
            mx=(cx+.5)*g.resolution;my=(cy+.5)*g.resolution
            candidate=[g.origin.position.x+math.cos(gh)*mx-math.sin(gh)*my,
                       g.origin.position.y+math.sin(gh)*mx+math.cos(gh)*my,ch+gh]
            print(f'Global scan candidate {candidate}, fit {fit:.3f}, alternate score {runner:.3f}',flush=True)
            matches=0
            continue
        pose=candidate
        score=scan_fit(pose,bx,by,g,walls)
        if score<.85:
            candidate=None;matches=0;continue
        matches+=1
        if matches<5 or pub.get_subscription_count()==0:continue
        x,y,h=candidate
        msg=PoseWithCovarianceStamped()
        msg.header.frame_id='map'
        msg.header.stamp=n.get_clock().now().to_msg()
        msg.pose.pose.position.x=x;msg.pose.pose.position.y=y
        msg.pose.pose.orientation.z=math.sin(h/2);msg.pose.pose.orientation.w=math.cos(h/2)
        for i,val in [(0,.025),(7,.025),(35,.015)]:msg.pose.covariance[i]=val
        pub.publish(msg);sent_at=now;candidate=None;matches=0
        print(f'Published globally matched initial pose {pose} (scan fit {score:.3f})',flush=True)

if __name__=='__main__':main()
