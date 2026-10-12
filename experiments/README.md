# 실험 기록 (`lab` 브랜치)

설정·알고리즘을 바꿔 본 실험의 조건, 결과, 결론을 남긴다. 채택한 변경만 `ktj`/`dev`로 옮긴다.

- 폴더 이름: `날짜_주제/`, 안에 `README.md`(조건·결과·결론·재현 방법)와 원본 CSV
- 시험 도구: `tools/sim_trials/` (사용법은 그 폴더 README)
- 진행 중인 작업 지시: `orders/`

| 날짜 | 실험 | 결론 |
|---|---|---|
| 2026-10-12 | [컨트롤러 MPPI vs RPP](2026-10-12_controller_mppi_vs_rpp/README.md) | MPPI 유지 (사람 있는 복도에서 RPP 6/12 중단) |
| 2026-10-12 | [학원 2층 순찰 반복 — 목표 앞 정지 재현](2026-10-12_patrol_repro/README.md) | 재현 안 됨 (10/10 OK). 위쪽 복도 3~5초 머뭇거림 4/9회, MPPI 쪽 |
| 2026-10-12 | [넓은 네모 맵 순찰 반복 (목표 앞 정지)](2026-10-12_patrol_repro_room/README.md) | 재현됨 3/10 실패. **원인 판단은 틀림** → 정지 waypoint 방향 문제 (원작자 PR #9, 기록 안 정정 참고) |
| 2026-10-12 | [MPPI 속도 튜닝](2026-10-12_mppi_speed/README.md) | `prune_distance` 1.7→2.5로 상자 구간 −26%, 복도 12/12 유지. vx_std·CostCritic은 효과 없음 |
