# 따라가기(limbo_follow follow_node)의 상태. 5 Hz로 /follow/state에 낸다 (PROJECT.md 2-9).
# person_wait는 active일 때 target_id 트랙을 기다리기 구역에서 뺀다(내 운용자 때문에 기다리지 않음). 나머지는 관제·로그용

std_msgs/Header header

string IDLE = "idle"            # 따라가기 안 함
string FOLLOWING = "following"  # 운용자를 보며 따라가는 중 (서 있는 것도 포함: 거리가 가까우면 제자리)
string HOLDING = "holding"      # 운용자를 놓쳐 마지막 본 자리로 가서 기다리는 중
string STOPPED = "stopped"      # 끝남 (정지 명령, 놓침 시간 초과, 주행 실패). reason에 이유

# 위 상수 중 하나
string state

# 참이면 FOLLOWING·HOLDING (Nav2 목표가 살아 있음)
bool active

# 운용자 트랙 번호 (FollowTarget.person_id). 없으면 -1
int32 target_id

# 로봇 중심 ↔ 운용자 거리 (m). 못 보면 마지막 값
float32 distance

# 이번 틱의 사유 (started, moving, near_hold, target_lost, lost_timeout, stop_requested, nav_failed 등)
string reason

# 지금 상태가 된 뒤 지난 시간 (s)
float32 elapsed_sec

# 놓친 뒤 지난 시간 (s). HOLDING일 때
float32 lost_sec

# 관제용 (3단계). 운용자가 등록돼 있는지 (/follow/enroll, FollowTarget.enrolled와 같음) — 시작 버튼 잠금 기준
bool enrolled

# 운용자가 최근(target_stale_sec 안)에 카메라에 보였는지 — 시작이 operator_not_visible로 거절될지 미리 보여 주는 용도
bool visible
