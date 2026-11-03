# 유한 모터 시험의 실제 움직임 판정

기존 `summary.json`의 `passed`는 실행·정지 절차 판정이다. 통신이 정상이어도 바퀴 카운트가 변하지 않는 회차가 실제로 발생했으므로, 이 값만으로 주행 성공을 판정하지 않는다.

`assess_motion_result.py`는 **이미 종료된 기록 파일만 읽는다.** ROS·직렬 장치·모터·보드 설정에 접근하지 않는다. 기존 원본과 `passed` 값을 덮어쓰지 않으며 별도의 결과를 만든다.

```sh
python3 /home/automaton/limbo/tools/motors/assess_motion_result.py \
  /home/automaton/limbo_pi_pwm_compare_20261103/records/pi_baseline_01 \
  --output /tmp/limbo_pi_baseline_01_motion.json
```

출력 파일이 이미 있으면 덮어쓰지 않는다. ROS 시험의 `node` 하위 폴더와 직접 PWM 기록을 모두 지원한다. 정상 통신 원본의 CRC/ACK와 전송 길이를 검사하며 손상·누락·실패 거래가 있으면 판정을 중단한다.

- `legacy_execution_passed`: 원본 실행 결과 그대로.
- `assessment`: 모든 구동 대상 바퀴의 움직임 / 무동작 / 일부 바퀴만 움직임을 구분.
- `motion_requirement_met`: 명령 방향으로 각 바퀴가5카운트 이상 진행하고 양의 카운트 증가가3표본 이상 관측됐는지 확인.
- `stop_verified`: 원본의 zero ACK·정지·포트 닫힘과 마지막 PWM0 응답을 함께 확인.
- `motion_and_stop_confirmed`: 위 움직임과 정지 조건을 모두 만족.
- `speed_tracking_assessed`: 항상 false. 목표 속도 추종은 별도 분석이 필요하다.

종료 코드는 움직임·정지 확인 시0, 그 외 정상 분석 결과는2, 파일/통신 증거 오류는 예외로 반환한다. 회전량 가드에 따른 원래 실패는 보존되므로, 움직임이 확인됐더라도 정상 시간 완주를 의미하지 않는다. 엔코더 움직임은 차체의 실제 이동거리나 미끄러짐 없는 주행을 독립적으로 증명하지 않으며, 무동작의 전기·기계·센서 원인을 특정하지 않는다.

2026-11-03 기준 설치된 모터 제어·게인·한도·RoboClaw 설정은 이 도구로 바뀌지 않는다. 이번 비교용 `manage.py collect`는 내려받은 기록에 이 판정을 자동으로 추가한다. 기존 ROS 노드의 실행 결과 형식 자체는 변경하지 않았다.
