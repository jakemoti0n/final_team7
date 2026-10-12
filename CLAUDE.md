# lab 브랜치 (실험실)

이 브랜치는 설정·알고리즘 실험용이다. 채택한 변경만 학원 컴퓨터(메인)가 `ktj`/`dev`로 옮긴다.

- **`dev`, `ktj`에 push하지 않는다.** 이 브랜치는 `git push origin lab`만
- 사용자는 한국어를 쓴다. 보고도 한국어로
- 작업 지시는 `experiments/orders/`에 있다. **상태가 `대기`인 지시서**를 찾아 그대로 수행하고, 끝나면 상태를 바꾸고 결과를 커밋·push한다
- 시험 도구: `tools/sim_trials/` (README 참고). 시뮬레이션은 `sim_ctl.sh`로 띄우고 끈다
- 프로세스는 PID나 `sim_ctl.sh stop`으로만 끈다. `pkill -f <패턴>`은 자기 셸까지 끌 수 있어서 쓰지 않는다
- rosbag 등 큰 파일은 커밋하지 않는다
- 저장소 문서: `docs/CHANGELOG.md`(변경 기록), `docs/KNOWN_ISSUES.md`(열린 문제), `docs/TROUBLESHOOTING.md`(해결한 문제), `experiments/`(실험 기록)
