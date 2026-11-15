import type { RobotData } from '../hooks/useRobotData'
import type { PageKey } from '../navigation'
import { Card } from '../components/Card'
import { PageLink } from '../components/PageLink'
import { PatrolCard } from '../features/status/PatrolCard'
import { MotionCard } from '../features/status/MotionCard'
import { MapCard } from '../features/map/MapCard'
import { Controls } from '../features/control/Controls'
import { AlertRow } from '../features/events/AlertRow'
import { Reception } from '../features/sensors/Reception'

/** 로봇 관제: 선택한 로봇 하나의 순찰·이동 상태, 지도, 제어, 알림, 센서 수신 */
export function ControlPage({ data, delta, onSelect, onNavigate }: { data: RobotData; delta: number; onSelect: (robotId: string) => void; onNavigate: (page: PageKey) => void }) {
  const { demo, view, live, map } = data
  const state = view.snapshot
  return <>
    <div className="summary"><PatrolCard view={view} /><MotionCard view={view} /></div>
    <div className="body-grid">
      <MapCard map={map} view={view} delta={delta} onSelect={demo ? undefined : onSelect} />
      <Controls demo={demo} live={live} view={view} delta={delta} routesLink={<PageLink page="routes" onNavigate={onNavigate}>순찰 경로 페이지</PageLink>} />
    </div>
    <Card title="최근 알림" className="alerts">{state?.alerts.length ? <ul>{state.alerts.map(alert => <AlertRow key={alert.id} alert={alert} />)}</ul> : <p className="empty">최근 알림이 없습니다</p>}</Card>
    <Reception state={state} serverProblem={view.serverProblem} delta={delta} />
  </>
}
