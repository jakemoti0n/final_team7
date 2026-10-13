# 순찰 노드(limbo_patrol)의 현재 상태. 상태가 바뀔 때마다 /patrol/state로 발행한다.
# 관제 화면은 정지·재개 명령의 결과를 이 상태로 확인한다 (docs/CONTROL_SCREEN.md A)

string WAITING_LOCALIZATION = "waiting_localization"
string PATROLLING = "patrolling"
string PAUSING = "pausing"
string PAUSED = "paused"
string COMPLETED = "completed"
string FAILED = "failed"

# 상태가 바뀐 시각 (명령 이후의 상태인지 판정할 때 씀)
builtin_interfaces/Time stamp

# 위 상수 중 하나
string state

# 다음 목표 waypoint (0부터 셈). 끝났으면 waypoint_count와 같다
uint32 waypoint_index
uint32 waypoint_count
string waypoint_name

# 재개할 순찰이 남아 있는지 (관제 화면의 재개 버튼 허용 기준)
bool has_resumable_task

# 마지막으로 상태가 바뀐 이유 (예: pause requested, Navigation failed)
string reason
