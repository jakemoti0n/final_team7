#!/bin/sh
# 컨테이너 시작: 설정 만들기 + waypoint 볼륨 준비 후 서버 실행
set -eu
: "${MAP_YAML:=limbo/src/limbo_navigation/maps/human_test_map.yaml}"
: "${INITIAL_WAYPOINTS:=test_waypoints.yaml}"
: "${VISITOR_ENABLED:=false}"
: "${INITIAL_GUIDE:=}"

# waypoint는 볼륨(/data)에 둔다. 컨테이너를 다시 만들어도 남는다. 볼륨이 비었을 때(처음)만 기본 파일을 복사
if [ ! -f /data/waypoints.yaml ]; then
  if [ ! -f "/srv/defaults/waypoints/$INITIAL_WAYPOINTS" ]; then
    echo "INITIAL_WAYPOINTS not found: $INITIAL_WAYPOINTS (choose one of: $(ls /srv/defaults/waypoints))" >&2
    exit 1
  fi
  cp "/srv/defaults/waypoints/$INITIAL_WAYPOINTS" /data/waypoints.yaml
  echo "waypoints: first start, copied $INITIAL_WAYPOINTS to /data/waypoints.yaml"
fi
# 방문자 안내 약도도 볼륨에 둔다(관제 화면 '약도 편집'이 저장). 처음에 INITIAL_GUIDE를 정했으면 그 파일을 복사,
# 아니면 파일 없이 시작해 화면에서 처음 저장할 때 만든다
if [ -n "$INITIAL_GUIDE" ] && [ ! -f /data/guide.yaml ]; then
  if [ ! -f "/srv/defaults/guides/$INITIAL_GUIDE" ]; then
    echo "INITIAL_GUIDE not found: $INITIAL_GUIDE (choose one of: $(cd /srv/defaults/guides && ls *.yaml 2>/dev/null))" >&2
    exit 1
  fi
  cp "/srv/defaults/guides/$INITIAL_GUIDE" /data/guide.yaml
  echo "guide: first start, copied $INITIAL_GUIDE to /data/guide.yaml"
fi
if [ ! -f "/srv/$MAP_YAML" ]; then
  echo "MAP_YAML not found: $MAP_YAML (choose one of: $(cd /srv && ls limbo/src/limbo_navigation/maps/*.yaml))" >&2
  exit 1
fi

case "$VISITOR_ENABLED" in
  true|false) ;;
  *) echo "VISITOR_ENABLED must be true or false (got: $VISITOR_ENABLED)" >&2; exit 1 ;;
esac

# 이미지 안 deploy/config.json에 지도와 방문자 화면 켜기만 바꿔 끼운다. 토큰은 환경 변수 ROBOT_TOKEN (없으면 서버가 시작 거부)
python - "$MAP_YAML" "$VISITOR_ENABLED" <<'PY'
import json, sys
config = json.load(open('/srv/dashboard/deploy/config.json'))
config['map_yaml'] = sys.argv[1]
config['visitor_enabled'] = sys.argv[2] == 'true'
json.dump(config, open('/tmp/dashboard-config.json', 'w'))
PY
export DASHBOARD_CONFIG=/tmp/dashboard-config.json
exec "$@"
