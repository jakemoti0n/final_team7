import type { View } from '../../types'
import { patrolLabel } from '../../status'
import { timeText } from '../../format'
import { Badge } from '../../components/Badge'
import { Card } from '../../components/Card'

export function PatrolCard({ view }: { view: View }) {
  const patrol = view.serverProblem ? null : view.snapshot?.patrol
  const state = patrol?.state
  const old = view.snapshot?.bridge.status !== 'connected'   // 마지막으로 받은 상태일 뿐 지금 상태가 아님
  const target = !patrol || !state ? '' : state === 'completed' ? `${patrol.waypoint_count}개 지점 모두 지남` : `다음 목표 ${patrol.waypoint_name || '—'} (${Math.min(patrol.waypoint_index + 1, patrol.waypoint_count)}/${patrol.waypoint_count})`
  // 받은 적은 있는데 상태가 없음 = 순찰 노드가 꺼졌거나 모르는 상태 (Bridge가 발행자가 없으면 비움)
  const lost = !!patrol && !state && patrol.update_count > 0
  const shown = state ? patrolLabel(state, patrol!.reason) : null
  return <Card title="순찰"><div className="movement patrol-state" role="status" data-testid="patrol-state">{shown ? <Badge status={state!} tone={old ? 'neutral' : shown.tone}>{shown.label}{old && ' (마지막 상태)'}</Badge> : lost ? <Badge status="lost" tone="warn">순찰 상태 확인 불가</Badge> : <Badge status="unknown">{view.serverProblem ? '현재 확인 불가' : '확인 전'}</Badge>}<span className="patrol-target">{target}</span></div>
    <p className="muted">{!patrol ? '순찰 상태 수신 대기' : old ? '로봇과 연결이 원활하지 않아 지금 상태는 알 수 없습니다' : lost ? '순찰 프로그램이 꺼져 있거나 상태를 알 수 없습니다' : state === 'failed' && patrol.reason ? `사유: ${patrol.reason}` : shown?.note ? shown.note : `마지막 상태 변경 ${timeText(patrol.last_received_at)}`}</p></Card>
}
