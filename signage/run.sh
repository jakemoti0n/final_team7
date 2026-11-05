#!/usr/bin/env bash
# 하단 디스플레이 실행. 인자는 그대로 넘긴다 (예: ./run.sh --windowed --mock)
# venv 위치는 SIGNAGE_VENV로 바꿀 수 있다 (기본: 저장소 루트의 venvs/signage/)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${SIGNAGE_VENV:-$HERE/../venvs/signage}"
cd "$HERE"
exec "$VENV/bin/python" -m app.main "$@"
