# syntax=docker/dockerfile:1
# 관제 서버 이미지: UI 빌드 → Python 서버. 빌드는 저장소 루트를 context로 (지도·기본 waypoint가 limbo/에 있음)
#   cd dashboard && docker compose build        (docker-compose.yml이 context: .. 로 지정)
# 배포 안내: docs/AWS_DEPLOY.md

FROM node:24-slim AS ui
WORKDIR /ui
RUN corepack enable
COPY dashboard/ui/package.json dashboard/ui/pnpm-lock.yaml ./
RUN corepack pnpm install --frozen-lockfile
COPY dashboard/ui/ ./
RUN corepack pnpm build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# 서버는 dashboard/의 부모(/srv)를 저장소 루트로 보므로 limbo/ 아래 상대경로가 그대로 맞는다
WORKDIR /srv/dashboard
COPY dashboard/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY dashboard/server ./server
COPY dashboard/deploy ./deploy
COPY --from=ui /ui/dist ./ui/dist
COPY limbo/src/limbo_navigation/maps/ /srv/limbo/src/limbo_navigation/maps/
COPY limbo/src/limbo_patrol/config/ /srv/defaults/waypoints/
# root가 아닌 사용자로 실행. /data(waypoint 볼륨)는 이 사용자 소유로 만들어 두면 새 볼륨이 그대로 물려받는다
RUN useradd --system --uid 10001 --home-dir /srv dashboard \
    && mkdir /data && chown dashboard:dashboard /data && chmod 755 deploy/entrypoint.sh
USER dashboard
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/srv/dashboard/deploy/entrypoint.sh"]
# 상태·명령 대기열이 프로세스 메모리에 있으므로 worker는 반드시 1
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
