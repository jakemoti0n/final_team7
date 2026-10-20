# 사람 기다리기 상태 기계(limbo_perception person_wait_node)의 결정. 10 Hz로 /person_wait에 낸다 (PROJECT.md 2-7).
# BT 조건 IsWaitingForPerson은 wait만 본다. 나머지는 관제·로그용

std_msgs/Header header

# NOT_READY | DRIVING | WAITING | PULL_OVER
string state

# 참이면 Nav2가 경로 추종을 멈추고 기다린다 (WAITING·PULL_OVER)
bool wait

# 이번 틱의 사유 (approaching, in_zone, stationary, zone_clear, no_pull_over_spot_15s 등)
string reason

# 로봇 앞 구역(범퍼 앞 zone_length × 진로 폭) 안의 사람 트랙 수
int32 tracks_in_zone

# 지금 상태가 된 뒤 지난 시간 (s)
float32 elapsed_sec

# 구역 안 사람이 모두 서 있은 시간 (s). service_sec가 지나면 비켜서기(R6) 또는 경보
float32 stationary_sec

# 비켜설 자리 없이 계속 기다리는 중의 경보 틱 (alarm_period_sec마다 한 번)
bool alarm

# 비켜서는 도중 사람이 움직여 비켜서기를 멈춰야 함 (R6 행동이 본다)
bool abort_pull_over
