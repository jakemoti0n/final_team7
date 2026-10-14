# lab 브랜치 (실험실)

이 브랜치는 설정·알고리즘 실험용이다. 채택한 변경만 **메인 PC**(이 노트북 `kim-laptop`)가 `ktj`/`dev`로 옮긴다. 컴퓨터는 둘뿐이다: 메인 PC(노트북)와 서브 PC(`automaton-desk`).

**먼저 `docs/PROJECT.md`를 읽는다.** 무엇을 만드는지, 바꾸면 안 되는 설계 전제, 무엇을 어디에 기록하는지가 거기 있다. 아래는 lab 브랜치에만 해당하는 규칙이다.

- **`dev`, `ktj`에 push하지 않는다.** 이 브랜치는 `git push origin lab`만
- 사용자는 한국어를 쓴다. 보고도 한국어로
- 두 컴퓨터의 소통 창구는 `docs/lab/` (예전 `docs/LAB_BOARD.md`는 쓰지 않음)
  - `docs/lab/requests.md`: 요청·답변. **메인 PC만 쓴다**
  - `docs/lab/reports.md`: 진행 상태·결과·질문. **서브 PC만 쓴다**
  - 상대 파일은 읽기만 한다. 같은 파일을 두 PC가 고치면 커밋이 충돌한다
- 서브 PC: `requests.md`에서 `reports.md` 진행 상태가 아직 없거나 `대기`인 요청을 수행한다. 긴 지시는 `experiments/orders/`에 있다
- push 전에 항상 `git pull --rebase origin lab`. **`git push --force` 금지**
- 실험 묶음(예: 10회 반복) 도중에는 pull하지 않는다. 시작 커밋 해시를 결과에 적고 끝난 뒤 pull한다
- 실험 결과 폴더 `experiments/<날짜>_<주제>/`는 그 실험을 한 PC만 쓴다
- 시험 도구: `tools/sim_trials/` (README 참고). 시뮬레이션은 `sim_ctl.sh`로 띄우고 끈다
- 프로세스는 PID나 `sim_ctl.sh stop`으로만 끈다. `pkill -f <패턴>`은 자기 셸까지 끌 수 있어서 쓰지 않는다
- rosbag 등 큰 파일은 커밋하지 않는다
- 저장소 문서: `docs/CHANGELOG.md`(변경 기록), `docs/KNOWN_ISSUES.md`(열린 문제), `docs/TROUBLESHOOTING.md`(해결한 문제), `experiments/`(실험 기록)
