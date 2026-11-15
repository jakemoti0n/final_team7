import type { Account, AuthState } from '../auth'
import type { RobotSummary } from '../types'
import { labels, overall } from '../status'
import { ageText, timeText } from '../format'
import { pages, type PageKey } from '../navigation'
import { Badge } from '../components/Badge'
import { useRobotData } from '../hooks/useRobotData'
import { RobotPicker } from '../features/header/RobotPicker'
import { AccountBar } from '../features/header/AccountBar'
import { DemoTools } from '../features/demo/DemoTools'
import { Sidebar } from '../features/shell/Sidebar'
import { ControlPage } from './ControlPage'
import { FleetPage } from './FleetPage'
import { RoutesPage } from './RoutesPage'

/**
 * 관제 화면 틀: 사이드바 + 상단 연결 상태 + 페이지. 로봇 하나의 실시간 데이터(useRobotData)를 여기서 한 번만 열어
 * 페이지를 오가도 연결·진행 중인 명령·데모 상태가 이어진다.
 */
export function RobotDashboard({ robotId, onSelect, account, onAuth, page, onNavigate }: { robotId: string; onSelect: (robotId: string) => void; account: Account | null; onAuth: (next: AuthState | null) => void; page: PageKey; onNavigate: (page: PageKey) => void }) {
  const data = useRobotData(robotId)
  const { demo, view, now, live } = data
  const state = view.snapshot
  const summary = overall(view)
  const delta = Math.max(0, (now - view.receivedMono) / 1000)
  const connection = view.serverProblem ? 'unknown' : state?.bridge.status ?? 'checking'
  const robotName = state?.robot_id ?? (robotId || 'LIMBO-01')
  const robots = state?.robots ?? [{ robot_id: robotName, status: connection === 'unknown' ? 'checking' : connection } as RobotSummary]
  const requestPending = !demo && live!.current(view)?.result === 'pending'
  const banner = view.serverProblem ? '서버 상태를 갱신할 수 없습니다. 현재 로봇 연결 상태를 확인할 수 없습니다.' : connection === 'disconnected' ? '로봇과 연결이 끊겼습니다. 아래 정보는 마지막으로 받은 상태입니다.' : connection === 'delayed' ? '로봇 상태가 늦게 오고 있습니다. 지금 상태는 확인할 수 없습니다.' : connection === 'checking' ? '로봇 연결을 확인하고 있습니다. 아직 받은 정보가 없습니다.' : null
  const info = pages.find(p => p.key === page)!
  return <>
    {demo && <div className="demo-banner">데모 데이터 · 실제 로봇을 제어하지 않습니다</div>}
    <div className="app-shell">
      <Sidebar page={page} onNavigate={onNavigate} demo={!!demo} picker={<RobotPicker current={robotName} robots={robots} pending={requestPending} disabled={!!demo} onSelect={onSelect} />} />
      <div className="app-main">
        <header className="topbar">
          <div className="page-title"><h1>{info.label}</h1><p>{demo ? `가상 로봇 · ${info.summary}` : info.summary}</p></div>
          <div className="connection" data-testid="connection"><span role="status" className="overall" data-testid="overall-status"><Badge status={summary.label} tone={summary.tone}>{summary.label}</Badge>{summary.detail && <span>{summary.detail}</span>}</span><span className="last-received" data-testid="last-received">{robotName} {labels[connection]} · {state?.bridge.last_received_at ? `마지막 수신 ${timeText(state.bridge.last_received_at)} · ${ageText(state.bridge.age_s, delta)}` : '수신 기록 없음'}</span></div>
          {account && <AccountBar account={account} onAuth={onAuth} />}
        </header>
        {banner && <div data-testid="banner" className={`banner ${connection}`} role={connection === 'checking' ? 'status' : 'alert'}><div className="page-inner">{banner}</div></div>}
        {demo && <DemoTools demo={demo} />}
        <main className="page-inner page-body">
          {page === 'control' && <ControlPage data={data} delta={delta} onSelect={onSelect} onNavigate={onNavigate} />}
          {page === 'fleet' && <FleetPage data={data} delta={delta} robotName={robotName} onSelect={onSelect} onNavigate={onNavigate} />}
          {page === 'routes' && <RoutesPage data={data} delta={delta} onNavigate={onNavigate} />}
          <footer data-testid="page-footer">{demo ? '데모의 상태 확인은 가상 이벤트에 기반합니다.' : `${robotName} · 수신 정보 기반 관제`}<span>표시 시각 Asia/Seoul</span></footer>
        </main>
      </div>
    </div>
  </>
}
