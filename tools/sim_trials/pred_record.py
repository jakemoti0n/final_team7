"""사람 예측을 map 좌표로 바꿔 녹화한다. 사용법: pred_record.py <출력.json> <초> <토픽>"""
import json, math, sys, time, rclpy
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener
from limbo_interfaces.msg import PersonPredictionArray
rclpy.init(); n = Node('pred_record_' + str(abs(hash(sys.argv[3])) % 1000)); buf = Buffer(); TransformListener(buf, n)
pending, rows = [], []
n.create_subscription(PersonPredictionArray, sys.argv[3], lambda m: pending.append(m), 50)
end = time.time() + float(sys.argv[2])
while time.time() < end or pending:
    rclpy.spin_once(n, timeout_sec=0.05)
    keep = []
    for m in pending:
        st = Time.from_msg(m.header.stamp)
        try:
            tf = buf.lookup_transform('map', m.header.frame_id, st)
        except Exception:
            if time.time() < end: keep.append(m)
            continue
        q = tf.transform.rotation; yaw = 2 * math.atan2(q.z, q.w); c, s = math.cos(yaw), math.sin(yaw)
        tx, ty = tf.transform.translation.x, tf.transform.translation.y
        to_map = lambda x, y: (tx + c * x - s * y, ty + s * x + c * y)
        for p in m.predictions:
            rows.append({'t': st.nanoseconds * 1e-9, 'id': p.person_id, 'pos': to_map(p.current_position.x, p.current_position.y),
                         'vel': (c * p.velocity.x - s * p.velocity.y, s * p.velocity.x + c * p.velocity.y)})
    pending = keep
json.dump(rows, open(sys.argv[1], 'w')); print(f'{sys.argv[3]}: {len(rows)}개')
