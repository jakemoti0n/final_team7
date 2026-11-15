import { useState } from 'react'
import { waypointLocked } from '../control'
import type { RobotData } from '../hooks/useRobotData'
import type { PageKey } from '../navigation'
import { Card } from '../components/Card'
import { PageLink } from '../components/PageLink'
import { PatrolCard } from '../features/status/PatrolCard'
import { MapCard } from '../features/map/MapCard'
import { WaypointPanel, type WaypointMode } from '../features/waypoints/WaypointPanel'

/** 순찰 경로: 지도에서 waypoint를 확인하고 추가·이동·이름 변경·순서 변경·삭제. 순찰 노드가 돌고 있으면 잠긴다 */
export function RoutesPage({ data, delta, onNavigate }: { data: RobotData; delta: number; onNavigate: (page: PageKey) => void }) {
  const { demo, view, live, map, waypointDocument, waypointProblem, changeWaypoint } = data
  // 편집 상태는 이 페이지에만 둔다. 다른 페이지로 가면 진행 중이던 지점 선택은 취소된다
  const [mode, setMode] = useState<WaypointMode | null>(null)
  const [picked, setPicked] = useState<[number, number] | null>(null)
  const locked = waypointLocked(view, demo ? demo.machine.current : live!.current(view))
  return <>
    <div className="summary">
      <PatrolCard view={view} />
      <Card title="경로 편집">
        <p role="status" data-testid="route-lock" className={`route-lock ${locked ? 'locked' : ''}`}>{locked
          ? <>순찰 노드가 실행 중이라 경로를 바꿀 수 없습니다. <PageLink page="control" onNavigate={onNavigate}>로봇 관제</PageLink>에서 순찰을 종료하면 편집할 수 있습니다.</>
          : '편집할 수 있습니다. 바꾼 경로는 다음 순찰 시작 때 로봇에 보내집니다.'}</p>
      </Card>
    </div>
    <div className="body-grid">
      <MapCard map={map} view={view} delta={delta} onPick={mode ? setPicked : undefined} title="순찰 지도" />
      <Card title="순찰 경로" className="routes">
        <div className="control-body"><WaypointPanel demo={demo} map={map} document={waypointDocument} locked={locked} problem={waypointProblem} onChange={changeWaypoint} mode={mode} picked={picked} setMode={setMode} setPicked={setPicked} /></div>
      </Card>
    </div>
  </>
}
