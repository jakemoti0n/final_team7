import type { RobotData } from '../hooks/useRobotData'
import type { PageKey } from '../navigation'
import type { Connection, RobotSummary } from '../types'
import { labels, patrolLabel } from '../status'
import { ageText, timeText } from '../format'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { MapCard } from '../features/map/MapCard'

type Shown = Connection | 'unknown'

/**
 * 플릿 현황: 서버가 아는 로봇 전체. 서버가 로봇마다 보내는 것은 연결 상태·마지막 수신·같은 지도 위 위치뿐이라
 * 그 밖의 값(배터리·적재량 등)은 그리지 않는다. 순찰 상태는 지금 선택한 로봇 것만 있다.
 */
export function FleetPage({ data, delta, robotName, onSelect, onNavigate }: { data: RobotData; delta: number; robotName: string; onSelect: (robotId: string) => void; onNavigate: (page: PageKey) => void }) {
  const { demo, view, map } = data
  const state = view.snapshot
  const self: RobotSummary = { robot_id: robotName, status: state?.bridge.status ?? 'checking', last_received_at: state?.bridge.last_received_at ?? null }
  const robots = state?.robots?.length ? state.robots : [self]
  // 브라우저↔서버가 끊기면 어느 로봇의 지금 상태도 알 수 없다
  const statusOf = (r: RobotSummary): Shown => view.serverProblem ? 'unknown' : r.robot_id === robotName ? state?.bridge.status ?? 'checking' : r.status
  const count = (wanted: Shown[]) => robots.filter(r => wanted.includes(statusOf(r))).length
  const serverMs = state ? Date.parse(state.server_utc) : NaN
  const age = (at: string | null | undefined) => !at || Number.isNaN(serverMs) ? null : Math.max(0, (serverMs - Date.parse(at)) / 1000)
  const open = (robotId: string) => { onNavigate('control'); if (robotId !== robotName) onSelect(robotId) }
  const patrol = view.serverProblem ? null : state?.patrol
  return <>
    <div className="fleet-kpis" role="group" aria-label="로봇 연결 요약">
      <Card title="등록된 로봇"><p className="kpi-value">{robots.length}<small>대</small></p><p className="muted">상태를 보낸 적이 있는 로봇</p></Card>
      <Card title="연결됨"><p className="kpi-value">{view.serverProblem ? '—' : count(['connected'])}<small>대</small></p><p className="muted">최근 {state?.settings.bridge_delay_s ?? 3}초 안에 상태를 받음</p></Card>
      <Card title="확인 필요"><p className="kpi-value">{view.serverProblem ? '—' : count(['delayed', 'checking'])}<small>대</small></p><p className="muted">수신 지연 · 연결 확인 중</p></Card>
      <Card title="연결 끊김"><p className="kpi-value">{view.serverProblem ? '—' : count(['disconnected'])}<small>대</small></p><p className="muted">{view.serverProblem ? '서버 상태를 갱신할 수 없어 확인 불가' : `${state?.settings.bridge_disconnect_s ?? 10}초 넘게 상태 없음`}</p></Card>
    </div>
    <div className="body-grid">
      <MapCard map={map} view={view} delta={delta} onSelect={demo ? undefined : onSelect} title="플릿 지도" />
      <Card title="로봇 목록" className="fleet-list">
        <ul aria-label="로봇 목록">{robots.map((r, i) => {
          const current = r.robot_id === robotName
          const pose = current ? (state?.pose?.x != null && state.pose.y != null ? { x: state.pose.x, y: state.pose.y, stale: state.pose.stale } : null) : r.pose
          const shown = current && patrol?.state ? patrolLabel(patrol.state, patrol.reason) : null
          const blocked = !!demo && !current
          return <li key={r.robot_id} data-testid="fleet-robot" className={current ? 'current' : ''}>
            <div className="fleet-robot-head"><span className="fleet-index" aria-hidden="true">{String(i + 1).padStart(2, '0')}</span><strong>{r.robot_id}</strong>{current && <span className="mode-tag">보는 중</span>}<Badge status={statusOf(r)}>{labels[statusOf(r)]}</Badge></div>
            <dl>
              <div><dt>마지막 수신</dt><dd>{r.last_received_at ? `${timeText(r.last_received_at)} · ${ageText(age(r.last_received_at), delta)}` : '수신 기록 없음'}</dd></div>
              <div><dt>위치</dt><dd>{pose ? `${pose.x.toFixed(2)}, ${pose.y.toFixed(2)} m${pose.stale ? ' (마지막 위치)' : ''}` : '같은 지도의 위치 없음'}</dd></div>
              {current && <div><dt>순찰</dt><dd>{shown ? shown.label : view.serverProblem ? '현재 확인 불가' : '순찰 상태 없음'}</dd></div>}
            </dl>
            <button type="button" disabled={blocked} onClick={() => open(r.robot_id)}>{current ? '관제 화면으로' : `${r.robot_id} 관제 보기`}</button>
            {blocked && <small>데모에서는 LIMBO-01만 관제할 수 있습니다.</small>}
          </li>
        })}</ul>
      </Card>
    </div>
  </>
}
