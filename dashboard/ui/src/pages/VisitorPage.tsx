import { Badge } from '../components/Badge'
import { ageText, timeText } from '../format'
import { useVisitorData } from '../features/visitor/useVisitorData'
import { VisitorMap } from '../features/visitor/VisitorMap'
import { GuideVisitorMap } from '../features/visitor/GuideVisitorMap'
import { dashedCircle, operatingText, positionAge, visitorStatus, type VisitorRobot } from '../features/visitor/visitor'

/**
 * 방문자 안내 (/visitor): 로그인 없이 휴대폰으로 보는 읽기 전용 화면. LIMBO가 어디 있는지만 알려 준다.
 * 적재량·내 위치·호출은 데이터가 없거나 위험해서 넣지 않았다 (ui/DESIGN.md 「방문자 안내」).
 */
export function VisitorPage({ demo }: { demo: boolean }) {
  const { state, receivedAt, problem, closed, now, guide } = useVisitorData(demo)
  const since = receivedAt === null ? 0 : (now - receivedAt) / 1000
  const where = (r: VisitorRobot) => {
    if (!r.position) return '위치 정보 없음'
    return problem || r.position.stale ? `마지막 위치 · ${ageText(positionAge(r.position, since))}` : '지도에 표시 중'
  }
  return <div className="visitor">
    {demo && <div className="demo-banner">데모 데이터 · 실제 로봇 위치가 아닙니다</div>}
    <header className="visitor-head"><div className="visitor-inner">
      <span className="brand-mark" aria-hidden="true">L</span>
      <div><h1>LIMBO 실시간 안내</h1><p>행사장을 순찰하는 스마트 쓰레기통 로봇 LIMBO가 지금 어디 있는지 알려 드립니다.</p></div>
    </div></header>
    {closed ? <main className="visitor-inner visitor-body"><section className="card visitor-closed" role="status" data-testid="visitor-closed">
      <h2 className="card-heading">지금은 안내를 하지 않습니다</h2><p>행사 기간에만 LIMBO 위치를 안내합니다.</p></section></main>
    : <main className="visitor-inner visitor-body">
      {problem && <div className="banner disconnected visitor-problem" role="alert" data-testid="visitor-problem">
        {state ? `정보를 새로 받을 수 없습니다. 아래는 ${ageText(since)}에 받은 정보입니다.` : '정보를 받을 수 없습니다. 3초마다 다시 시도합니다.'}</div>}
      <p className="visitor-count" role="status" data-testid="visitor-count">{operatingText(state, problem)}</p>
      {state && (guide || state.map) && <section className="card visitor-card" aria-label="지금 LIMBO 위치">
        <h2 className="card-heading">지금 LIMBO 위치</h2>
        {/* 안내 약도가 있으면 그것이 메인(실제 LiDAR 지도는 탭으로 바꿔 봄), 없으면 자동 약도 */}
        {guide ? <GuideVisitorMap guide={guide} map={state.map} robots={state.robots} stale={problem} /> : <VisitorMap map={state.map!} robots={state.robots} stale={problem} />}
        <p className="visitor-legend" data-testid="visitor-legend"><span><i className="key now" />지금 위치</span><span>{/* CSS dashed 테두리는 iOS Safari에서 둥근 모서리가 반쪽만 그려지므로 SVG로 그린다 */}<svg className="key-old" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" strokeDasharray={dashedCircle(6.5, 8)} /></svg>마지막으로 확인한 위치</span></p>
      </section>}
      {state && <section className="card visitor-card" aria-label="로봇 목록">
        <h2 className="card-heading">로봇 목록</h2>
        <ul className="visitor-list">{state.robots.map(r => <li key={r.robot_id} data-testid="visitor-robot">
          <strong>{r.robot_id}</strong>
          <Badge status={r.status} tone={problem ? 'neutral' : visitorStatus[r.status].tone}>{problem ? '확인 불가' : visitorStatus[r.status].label}</Badge>
          <small>{where(r)}</small>
        </li>)}</ul>
      </section>}
      <footer className="visitor-foot" data-testid="visitor-foot">
        <span>위치는 약 0.5 m 단위로 표시하며 {demo ? '가상 데이터입니다' : '3초마다 새로 받습니다'}.</span>
        {state && <span>받은 시각 {timeText(state.server_utc)} (Asia/Seoul)</span>}
      </footer>
    </main>}
  </div>
}
