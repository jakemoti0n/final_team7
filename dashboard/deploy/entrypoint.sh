#!/bin/sh
# 컨테이너 시작: 설정 만들기 + waypoint 볼륨 준비 후 서버 실행
set -eu
: "${MAP_YAML:=limbo/src/limbo_navigation/maps/human_test_map.yaml}"
: "${INITIAL_WAYPOINTS:=test_waypoints.yaml}"

# waypoint는 볼륨(/data)에 둔다. 컨테이너를 다시 만들어도 남는다. 볼륨이 비었을 때(처음)만 기본 파일을 복사
if [ ! -f /data/waypoints.yaml ]; then
  if [ ! -f "/srv/defaults/waypoints/$INITIAL_WAYPOINTS" ]; then
    echo "INITIAL_WAYPOINTS not found: $INITIAL_WAYPOINTS (choose one of: $(ls /srv/defaults/waypoints))" >&2
    exit 1
  fi
  cp "/srv/defaults/waypoints/$INITIAL_WAYPOINTS" /data/waypoints.yaml
  echo "waypoints: first start, copied $INITIAL_WAYPOINTS to /data/waypoints.yaml"
fi
if [ ! -f "/srv/$MAP_YAML" ]; then
  echo "MAP_YAML not found: $MAP_YAML (choose one of: $(cd /srv && ls limbo/src/limbo_navigation/maps/*.yaml))" >&2
  exit 1
fi

# 이미지 안 deploy/config.json에 지도만 바꿔 끼운다. 토큰은 환경 변수 ROBOT_TOKEN (없으면 서버가 시작 거부)
python - "$MAP_YAML" <<'PY'
import json, sys
config = json.load(open('/srv/dashboard/deploy/config.json'))
config['map_yaml'] = sys.argv[1]
json.dump(config, open('/tmp/dashboard-config.json', 'w'))
PY
export DASHBOARD_CONFIG=/tmp/dashboard-config.json
exec "$@"
