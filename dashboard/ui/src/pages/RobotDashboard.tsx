import { useState } from 'react'
import type { Account, AuthState } from '../auth'
import type { RobotSummary } from '../types'
import { labels, overall } from '../status'
import { ageText, timeText } from '../format'
import { Badge } from '../components/Badge'
import { Card } from '../components/Card'
import { useRobotData } from '../hooks/useRobotData'
import { RobotPicker } from '../features/header/RobotPicker'
import { AccountBar } from '../features/header/AccountBar'
import { DemoTools } from '../features/demo/DemoTools'
import { PatrolCard } from '../features/status/PatrolCard'
import { MapCard } from '../features/map/MapCard'
import { Controls } from '../features/control/Controls'
import { AlertRow } from '../features/events/AlertRow'
import { Reception } from '../features/sensors/Reception'
import type { WaypointMode } from '../features/waypoints/WaypointPanel'

export function RobotDashboard({ robotId, onSelect, account, onAuth }: { robotId: string; onSelect: (robotId: string) => void; account: Account | null; onAuth: (next: AuthState | null) => void }) {
  const { demo, view, now, live, map, waypointDocument, waypointProblem, changeWaypoint } = useRobotData(robotId)
  const [waypointMode, setWaypointMode] = useState<WaypointMode | null>(null)
  const [picked, setPicked] = useState<[number, number] | null>(null)
  const state = view.snapshot
  const summary = overall(view)
  const delta = Math.max(0, (now - view.receivedMono) / 1000)
  const connection = view.serverProblem ? 'unknown' : state?.bridge.status ?? 'checking'
  const motionStatus = view.serverProblem ? 'unknown' : state?.motion.status ?? 'unconfirmed'
  const current = view.serverProblem ? null : state?.motion.current
  const value = current ?? state?.motion.last_valid
  const retained = !!value && !current
  const robotName = state?.robot_id ?? (robotId || 'LIMBO-01')
  const robots = state?.robots ?? [{ robot_id: robotName, status: connection === 'unknown' ? 'checking' : connection } as RobotSummary]
  const requestPending = !demo && live!.current(view)?.result === 'pending'
  const banner = view.serverProblem ? '서버 상태를 갱신할 수 없습니다. 현재 로봇 연결 상태를 확인할 수 없습니다.' : connection === 'disconnected' ? '로봇과 연결이 끊겼습니다. 아래 정보는 마지막으로 받은 상태입니다.' : connection === 'delayed' ? '로봇 상태가 늦게 오고 있습니다. 지금 상태는 확인할 수 없습니다.' : connection === 'checking' ? '로봇 연결을 확인하고 있습니다. 아직 받은 정보가 없습니다.' : null
  return <>
    {demo && <div className="demo-banner">데모 데이터 · 실제 로봇을 제어하지 않습니다</div>}
    <header><div className="container header-inner"><div className="brand"><h1>LIMBO 관제</h1><RobotPicker current={robotName} robots={robots} pending={requestPending} disabled={!!demo} onSelect={onSelect} />{demo && <span className="mode-tag">데모 데이터</span>}</div><div className="connection" data-testid="connection"><span role="status" className="overall" data-testid="overall-status"><Badge status={summary.label} tone={summary.tone}>{summary.label}</Badge>{summary.detail && <span>{summary.detail}</span>}</span><span className="last-received" data-testid="last-received">로봇 {labels[connection]} · {state?.bridge.last_received_at ? `마지막 수신 ${timeText(state.bridge.last_received_at)} · ${ageText(state.bridge.age_s, delta)}` : '수신 기록 없음'}</span></div>{account && <AccountBar account={account} onAuth={onAuth} />}</div></header>
    {banner && <div data-testid="banner" className={`banner ${connection}`} role={connection === 'checking' ? 'status' : 'alert'}><div className="container">{banner}</div></div>}
    {demo && <DemoTools demo={demo} />}
    <main className="container"><div className="page-meta"><span>{demo ? '가상 로봇 상태 및 제어 흐름 검증' : '로봇 상태 모니터링 · 순찰 제어'}</span><a href={demo ? '/' : '/demo'}>{demo ? '실제 수신 화면으로 →' : '가상 제어 데모 보기 →'}</a></div>
      <div className="summary"><PatrolCard view={view} />
        <Card title="이동"><div className="movement" role="status" data-testid="motion-state"><Badge status={motionStatus} />{!view.serverProblem && state?.motion.rotating && <span>회전 중</span>}
          <div data-testid="speed" className={`speed ${retained ? 'muted' : ''}`}><strong data-testid="speed-value">{value ? value.linear_speed_mps.toFixed(2) : '—'}</strong><span>m/s</span>{retained && <Badge status="unknown">마지막 수신 값</Badge>}</div></div>
          <p className="muted">{value ? `주행 정보 ${timeText(value.last_received_at)} 기준 추정값` : '유효한 주행 정보 수신 대기'} · 멈춰 있다고 일시정지가 확인된 것은 아닙니다</p></Card></div>
      <div className="body-grid"><MapCard map={map} view={view} delta={delta} onPick={waypointMode ? setPicked : undefined} onSelect={demo ? undefined : onSelect} /><Controls demo={demo} live={live} view={view} delta={delta} map={map} waypointDocument={waypointDocument} waypointProblem={waypointProblem} changeWaypoint={changeWaypoint} waypointMode={waypointMode} picked={picked} setWaypointMode={setWaypointMode} setPicked={setPicked} /></div>
      <Card title="최근 알림" className="alerts">{state?.alerts.length ? <ul>{state.alerts.map(alert => <AlertRow key={alert.id} alert={alert} />)}</ul> : <p className="empty">최근 알림이 없습니다</p>}</Card>
      <Reception state={state} serverProblem={view.serverProblem} delta={delta} />
      <footer data-testid="page-footer">{demo ? '데모의 상태 확인은 가상 이벤트에 기반합니다.' : `${robotName} · 수신 정보 기반 관제`}<span>표시 시각 Asia/Seoul</span></footer>
    </main>
  </>
}
