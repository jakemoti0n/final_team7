#!/usr/bin/env bash
# 합성 bag으로 기록 → 데이터셋 → 학습 → 정책 노드 흐름을 한 번 돌린다(Gazebo 없이). pytest 밖의 확인용.
#   bash test/e2e_synthetic.sh [작업 폴더]
# 환경 변수 LIMBO_TORCH_PYTHON: torch가 있는 파이썬(기본 python3). 학습과 policy_node에 쓴다(.pt 읽기에 torch 필요).
#           POLICY_BACKEND: policy_node backend(torch 기본, numpy).
# 다른 실행과 섞이지 않게 ROS_DOMAIN_ID 93. 띄운 프로세스는 저장한 PID로만 끝낸다(패턴 kill 금지).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd "$HERE/../../.." && pwd)"
WORK="${1:-$(mktemp -d)}"
PY="${LIMBO_TORCH_PYTHON:-python3}"
export ROS_DOMAIN_ID=93
export PYTHONUNBUFFERED=1 RCUTILS_LOGGING_BUFFERED_STREAM=0  # 로그 파일을 기다리며 읽으므로 바로 쓰게
LAPS=3
ECHO_TIMEOUT=10
TIMING_WAIT=15  # s. 상한일 뿐. policy_node가 처리 시간을 10 s(timing_log_period)마다 남기면 바로 넘어간다
POLL=0.5

set +u
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"
set -u

PIDS=()
cleanup() {
  for pid in "${PIDS[@]}"; do
    kill -INT "$pid" 2>/dev/null || true
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

echo "== 1. 합성 바퀴 $LAPS개 → $WORK/runs"
rm -rf "$WORK/runs"
for seed in $(seq 1 "$LAPS"); do
  python3 "$HERE/make_synthetic_bag.py" "$WORK/runs" --seed "$seed" >/dev/null
done
RUNS=("$WORK"/runs/2*/)

echo "== 2. build_dataset"
ros2 run limbo_imitation build_dataset "${RUNS[@]}" -o "$WORK/data.npz" --val-fraction 0.34

echo "== 3. train_policy ($PY)"
"$PY" -m limbo_imitation.train "$WORK/data.npz" -o "$WORK/policy.pt"

# /patrol/state는 patrol_node가 transient_local로 낸다(상태가 바뀔 때만 오는 래치 토픽).
# 합성 bag에는 QoS가 안 실려 재생 때 같은 QoS를 준다. 그래야 늦게 붙은 policy_node도 받는다
cat >"$WORK/qos_overrides.yaml" <<'QOS'
/patrol/state:
  history: keep_last
  depth: 1
  reliability: reliable
  durability: transient_local
QOS

echo "== 4. policy_node + ros2 bag play --clock"
"$PY" -m limbo_imitation.policy_node --ros-args -p use_sim_time:=true \
  -p backend:="${POLICY_BACKEND:-torch}" -p model_path:="$WORK/policy.pt" -p waypoints_file:="$WORK/runs/synthetic_waypoints.yaml" \
  >"$WORK/policy_node.log" 2>&1 &
PIDS+=($!)
timeout "$ECHO_TIMEOUT" bash -c "until ros2 node list 2>/dev/null | grep -qx /policy_node; do sleep $POLL; done"
ros2 bag play "${RUNS[0]}bag" --clock --qos-profile-overrides-path "$WORK/qos_overrides.yaml" \
  --topics /scan /odom /tf /patrol/state /person_detector/predictions \
  >"$WORK/bag_play.log" 2>&1 &
PIDS+=($!)

echo "-- /cmd_vel_policy"
timeout "$ECHO_TIMEOUT" ros2 topic echo /cmd_vel_policy geometry_msgs/msg/Twist --once
echo "-- /policy/status"
timeout "$ECHO_TIMEOUT" ros2 topic echo /policy/status std_msgs/msg/String --once
echo "-- /policy/status ok=true 기다림"
# grep이 먼저 끝나면 echo가 SIGPIPE로 끝나 pipefail에 걸리므로 이 줄만 pipefail을 끈다
(set +o pipefail; timeout "$ECHO_TIMEOUT" ros2 topic echo /policy/status std_msgs/msg/String \
  --field data 2>/dev/null | grep -m1 '"ok": true')
echo "-- policy_node 처리 시간 로그 기다림"
timeout "$TIMING_WAIT" bash -c "until grep -q 'processing time' '$WORK/policy_node.log'; do sleep $POLL; done"
cat "$WORK/policy_node.log"
echo "== e2e OK ($WORK)"
