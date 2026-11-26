"""record_laps가 부르는 ROS 확인 세 가지. 사람이 직접 칠 일은 없다.

    python3 record_laps_checks.py sensors          # /odom·/scan·카메라가 실제로 오는지, 기록 런치가 이미 떠 있지 않은지
    python3 record_laps_checks.py manual_wiring    # collision_monitor가 /cmd_vel_arbiter를 받고 Nav2가 active인지
    python3 record_laps_checks.py slots mode:=manual driver:=<이름>   # 기록 런치를 더 띄워도 발견 포트 슬롯 범위 안인지

종료 코드 0 = 통과. 0이 아니면 stdout 마지막 줄이 사람에게 보여 줄 한국어 이유다.
기다리는 동안의 안내도 한 줄씩 stdout으로 낸다(같은 안내는 한 번만).

판단은 모두 상태 신호로 한다. "몇 초 기다리면 된다" 같은 고정 대기는 없다.
확인 간격 2 s는 부팅 스크립트(start, wait_clock)의 폴링 간격과 같다.

주의: sensors·manual_wiring은 새 DDS 참여자로 본다. 확인 대상은 일찍 뜬 부팅 유닛 노드(센서·Nav2)로만 하고,
기록 런치 노드는 record_laps가 노드 로그로 확인한다(발견 범위 밖에서 뜬 노드는 그래프로 안 보일 수 있어서,
TROUBLESHOOTING 2026-11-26 DDS 포트 슬롯).
"""

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import rclpy
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, LaserScan
from std_srvs.srv import Trigger

POLL_S = 2.0

# (토픽, 메시지 형, 그 토픽을 내는 부팅 유닛, 사람에게 보여 줄 이름)
SENSOR_TOPICS = [
    ('/odom', Odometry, 'limbo-nx-drive', '바퀴 위치(/odom)'),
    ('/scan', LaserScan, 'limbo-nx-sensors', '라이다(/scan)'),
    ('/rgbd_camera/image', Image, 'limbo-nx-sensors', '카메라(/rgbd_camera/image)'),
]
# 기록 런치(imitation_real.launch.py)의 노드. 이게 이미 있으면 패드 명령이 두 벌 나간다
RECORD_LAUNCH_NODES = ('joy_node', 'drive_arbiter', 'run_recorder')
NAV2_READY_SERVICE = '/lifecycle_manager_navigation/is_active'


def unit_state(unit):
    result = subprocess.run(['systemctl', '--user', 'is-active', unit],
                            capture_output=True, text=True)
    return result.stdout.strip()


class Announcer:
    """같은 안내를 2 s마다 되풀이하지 않게, 바뀔 때만 한 줄 찍는다."""

    def __init__(self):
        self.last = None

    def say(self, line):
        if line != self.last:
            print(line, flush=True)
            self.last = line


class SensorWatch:
    """토픽 하나: 발행자와 이어졌는지(발견), 이어진 뒤 메시지가 왔는지."""

    def __init__(self, node, topic, msg_type, unit, label):
        self.topic, self.unit, self.label = topic, unit, label
        self.received = False
        self.matched_at_tick = None
        # sensor_data QoS(best effort)는 reliable 발행자와도 이어진다. 발행자 QoS를 몰라도 된다
        self.sub = node.create_subscription(msg_type, topic, self.on_msg, qos_profile_sensor_data)

    def on_msg(self, _msg):
        self.received = True

    def verdict(self, tick):
        """'ok' / 'starting'(발행자 아직 없음) / 'silent'(이어졌는데 한 간격 내내 메시지 없음) / 'unit_down'."""
        if self.received:
            return 'ok'
        if self.sub.get_publisher_count() == 0:
            self.matched_at_tick = None
            return 'starting' if unit_state(self.unit) == 'active' else 'unit_down'
        if self.matched_at_tick is None:
            self.matched_at_tick = tick
            return 'starting'
        # 이어진 뒤 한 간격(2 s, 10 Hz 토픽이면 20번 나올 시간) 동안 한 개도 안 왔다
        return 'silent' if tick > self.matched_at_tick else 'starting'


def spin_until(node, announcer, on_tick):
    """POLL_S마다 on_tick(tick)을 부른다. on_tick이 (끝, 코드, 줄)을 돌려주면 멈춘다."""
    tick = 0
    while rclpy.ok():
        end = node.get_clock().now().nanoseconds + int(POLL_S * 1e9)
        while node.get_clock().now().nanoseconds < end:
            rclpy.spin_once(node, timeout_sec=0.1)
        tick += 1
        finished, code, line = on_tick(tick)
        if finished:
            if line:
                print(line, flush=True)
            return code
        if line:
            announcer.say(line)
    return 1


def check_sensors(node):
    watches = [SensorWatch(node, *spec) for spec in SENSOR_TOPICS]
    announcer = Announcer()

    def on_tick(tick):
        waiting = []
        for w in watches:
            v = w.verdict(tick)
            if v == 'unit_down':
                return True, 1, f'{w.label}를 내는 {w.unit} 유닛이 꺼져 있다({unit_state(w.unit)}). PM에게 알린다'
            if v == 'silent':
                return True, 1, f'{w.label}: 발행자는 있는데 메시지가 안 온다. PM에게 알린다'
            if v == 'starting':
                waiting.append(w.label)
        if waiting:
            return False, 0, '센서가 뜨기를 기다리는 중: ' + ', '.join(waiting)
        running = [n for n in RECORD_LAUNCH_NODES if n in node.get_node_names()]
        if running:
            return True, 1, ('기록 런치가 이미 다른 창에 떠 있다(' + ', '.join(running) +
                             '). 그 창에서 Ctrl+C로 끈 뒤 다시 친다')
        return True, 0, '센서 확인: ' + ', '.join(w.label for w in watches) + ' 모두 들어옴'

    return spin_until(node, announcer, on_tick)


def nav2_reports_active(node, client):
    """lifecycle_manager_navigation이 관리하는 노드가 모두 active면 True(로그의 'Managed nodes are active'와 같은 상태)."""
    if not client.service_is_ready():
        return False
    future = client.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(node, future, timeout_sec=POLL_S)
    return future.done() and future.result() is not None and future.result().success


def check_manual_wiring(node):
    client = node.create_client(Trigger, NAV2_READY_SERVICE)
    announcer = Announcer()

    def on_tick(_tick):
        state = unit_state('limbo-nx-navigation')
        if state != 'active':
            return True, 1, f'limbo-nx-navigation 유닛이 꺼져 있다({state}). PM에게 알린다'
        subs = [i.node_name for i in node.get_subscriptions_info_by_topic('/cmd_vel_arbiter')]
        if 'collision_monitor' in subs and nav2_reports_active(node, client):
            return True, 0, 'Nav2 준비됨: collision_monitor가 패드 명령(/cmd_vel_arbiter)을 받는다'
        return False, 0, 'Nav2가 다시 뜨기를 기다리는 중(위치 확인 → Nav2 기동 순서로 뜬다)'

    return spin_until(node, announcer, on_tick)


# ---------------------------------------------------------------- 발견 포트 슬롯
#
# 같은 보드의 ROS 프로세스(DDS 참여자)는 저마다 비어 있는 가장 낮은 "포트 슬롯"을 잡는다.
# 발견 알림은 127.0.0.1의 슬롯 0 ~ (범위-1) 포트로만 보내므로, 두 프로세스가 모두 범위 밖이면 서로 못 찾는다.
# 범위는 숫자로 박지 않고, 지금 쓰는 Fast DDS XML(FASTRTPS_DEFAULT_PROFILES_FILE)과 rmw 값 중 큰 쪽이다.

# rmw_fastrtps_shared_cpp(jazzy) src/participant.cpp: ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST일 때
# `udp_transport->maxInitialPeersRange = 32`인 UDP 전송을 XML 전송 뒤에 덧붙인다. 전송마다 초기 피어를 만들므로
# 실제 범위는 XML 값과 이 값 중 큰 쪽이다.
RMW_LOCALHOST_PEERS_RANGE = 32
# RTPS 2.2 9.6.1.1 기본 포트 식(Fast DDS PortParameters 기본값):
# 발견(메타 트래픽) 유니캐스트 포트 = PB + DG×도메인 + d1 + PG×슬롯
PORT_BASE, DOMAIN_GAIN, OFFSET_D1, PARTICIPANT_GAIN = 7400, 250, 10, 2
# run_recorder.prepare_standby: 다음 바퀴용 `ros2 bag record`(일시 정지)를 자식 프로세스로 하나 띄워 둔다.
# 런치가 뜰 때 바로 하나, 바퀴가 끝나면 그 bag을 거둔 뒤에 다음 하나라 동시에 하나다.
# 런치 파일에는 안 보이는 프로세스라 런치에서 세지 못해 여기 둔다
RECORDER_CHILD_PROCESSES = 1


def udp_peers_range_in_xml(path):
    """XML의 UDPv4 전송 기술자에 적힌 maxInitialPeersRange 중 가장 큰 값. 없으면 None."""
    ns = '{http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles}'
    values = []
    for descriptor in ET.parse(path).getroot().iter(ns + 'transport_descriptor'):
        kind = descriptor.findtext(ns + 'type', '').strip()
        value = descriptor.findtext(ns + 'maxInitialPeersRange')
        if kind == 'UDPv4' and value is not None:
            values.append(int(value))
    return max(values) if values else None


def discovery_peers_range():
    """(범위, 설명). 이 보드의 프로세스가 발견 알림을 보내는 슬롯 수."""
    if os.environ.get('ROS_AUTOMATIC_DISCOVERY_RANGE') != 'LOCALHOST':
        return None, 'ROS_AUTOMATIC_DISCOVERY_RANGE가 LOCALHOST가 아니다'
    xml_path = os.environ.get('FASTRTPS_DEFAULT_PROFILES_FILE', '')
    if not os.path.isfile(xml_path):
        return None, f'Fast DDS XML이 없다({xml_path or "FASTRTPS_DEFAULT_PROFILES_FILE 비어 있음"})'
    xml_range = udp_peers_range_in_xml(xml_path)
    found = max(RMW_LOCALHOST_PEERS_RANGE, xml_range or 0)
    return found, f'XML {xml_range}, rmw {RMW_LOCALHOST_PEERS_RANGE} → {found} ({xml_path})'


def occupied_slots(domain):
    """지금 열려 있는 이 도메인의 발견 포트 슬롯 번호들(ss -Huln)."""
    first = PORT_BASE + DOMAIN_GAIN * domain + OFFSET_D1
    # 다음 도메인 포트 앞까지만 이 도메인의 슬롯이다
    slot_limit = (DOMAIN_GAIN - OFFSET_D1) // PARTICIPANT_GAIN
    out = subprocess.run(['ss', '-Huln'], capture_output=True, text=True, check=True).stdout
    slots = set()
    for line in out.splitlines():
        fields = line.split()
        match = re.search(r':(\d+)$', fields[3]) if len(fields) > 3 else None
        if not match:
            continue
        offset = int(match.group(1)) - first
        if 0 <= offset < slot_limit * PARTICIPANT_GAIN and offset % PARTICIPANT_GAIN == 0:
            slots.add(offset // PARTICIPANT_GAIN)
    return sorted(slots)


def launch_process_count(launch_args):
    """기록 런치(imitation_real.launch.py)가 이 인자로 띄울 노드 수. 조건(IfCondition)까지 평가해서 센다."""
    from ament_index_python.packages import get_package_share_directory
    from launch import LaunchContext
    from launch.actions import DeclareLaunchArgument, ExecuteProcess
    from launch.launch_description_sources import PythonLaunchDescriptionSource
    from launch.utilities import perform_substitutions

    path = os.path.join(get_package_share_directory('limbo_imitation'), 'launch',
                        'imitation_real.launch.py')
    description = PythonLaunchDescriptionSource(path).get_launch_description(LaunchContext())
    context = LaunchContext()
    context.launch_configurations.update(launch_args)
    count = 0
    for entity in description.entities:
        if isinstance(entity, DeclareLaunchArgument):
            if entity.name not in context.launch_configurations and entity.default_value:
                context.launch_configurations[entity.name] = perform_substitutions(
                    context, entity.default_value)
        elif isinstance(entity, ExecuteProcess):  # launch_ros Node도 ExecuteProcess다
            if entity.condition is None or entity.condition.evaluate(context):
                count += 1
        else:
            # 포함 런치·그룹 등은 이 셈법으로 못 센다. 런치가 바뀌었으면 이 함수도 고친다
            raise ValueError(f'{type(entity).__name__}는 셀 수 없다({path})')
    return count


def check_slots(launch_argv):
    peers_range, how = discovery_peers_range()
    if peers_range is None:
        print(f'발견 범위를 읽지 못했다: {how}. PM에게 알린다', flush=True)
        return 1
    launch_args = dict(arg.split(':=', 1) for arg in launch_argv if ':=' in arg)
    try:
        new = launch_process_count(launch_args) + RECORDER_CHILD_PROCESSES
    except ValueError as error:
        print(f'기록 런치 프로세스 수를 세지 못했다: {error}. PM에게 알린다', flush=True)
        return 1
    slots = occupied_slots(int(os.environ.get('ROS_DOMAIN_ID', '0')))
    highest = slots[-1] if slots else -1
    # 새 프로세스는 빈 가장 낮은 슬롯부터 잡으므로 최고 슬롯 + 새 프로세스 수를 넘지 않는다(보수적으로 잡은 상한)
    worst = highest + new
    summary = (f'포트 슬롯 {len(slots)}개 사용 중(최고 {highest}), 기록 런치 {new}개 추가 → 최고 {worst}, '
               f'발견 범위 0~{peers_range - 1} [{how}]')
    if worst >= peers_range:
        print(f'{summary}. 범위를 넘으면 기록에 토픽이 빠질 수 있어 시작하지 않는다. PM에게 알린다', flush=True)
        return 1
    print(f'발견 범위 확인: {summary}', flush=True)
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'slots':
        # ROS 노드를 만들지 않는다(만들면 그 자체가 슬롯 하나를 잡는다)
        return check_slots(sys.argv[2:])
    # 신호 처리는 record_laps(bash)가 한다. rclpy가 SIGINT를 가로채지 않게 한다
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('record_laps_check')
    try:
        if mode == 'sensors':
            return check_sensors(node)
        if mode == 'manual_wiring':
            return check_manual_wiring(node)
        print(__doc__)
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    sys.exit(main())
