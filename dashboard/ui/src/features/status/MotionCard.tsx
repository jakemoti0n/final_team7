import type { View } from '../../types'
import { timeText } from '../../format'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'

/** 이동 카드: 속도와 이동·정지 상태. 받지 못하면 "—", 마지막 값은 흐리게 + "마지막 수신 값" */
export function MotionCard({ view }: { view: View }) {
  const state = view.snapshot
  const motionStatus = view.serverProblem ? 'unknown' : state?.motion.status ?? 'unconfirmed'
  const current = view.serverProblem ? null : state?.motion.current
  const value = current ?? state?.motion.last_valid
  const retained = !!value && !current
  return <Card title="이동"><div className="movement" role="status" data-testid="motion-state"><Badge status={motionStatus} />{!view.serverProblem && state?.motion.rotating && <span>회전 중</span>}
    <div data-testid="speed" className={`speed ${retained ? 'muted' : ''}`}><strong data-testid="speed-value">{value ? value.linear_speed_mps.toFixed(2) : '—'}</strong><span>m/s</span>{retained && <Badge status="unknown">마지막 수신 값</Badge>}</div></div>
    <p className="muted">{value ? `주행 정보 ${timeText(value.last_received_at)} 기준 추정값` : '유효한 주행 정보 수신 대기'} · 멈춰 있다고 일시정지가 확인된 것은 아닙니다</p></Card>
}
