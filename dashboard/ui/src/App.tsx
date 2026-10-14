import { useEffect, useReducer, useState, type ReactNode } from 'react'
import { LiveProvider } from './live'
import { MockProvider, demoMap, scenarios, type Patrol, type Scenario } from './demo'
import { commandNames, resultLabels, type Command, type Outcome, type RequestResult } from './commands'
import { LiveControl, lockReason, pauseReason, resumeReason } from './control'
import { headingDeg, isMapInfo, toPixel, uncertaintyPx, type MapInfo } from './map'
import { names, topicKeys, type Provider, type Snapshot, type View } from './types'

export function ageText(age: number | null, delta = 0) {
  if (age === null) return '—'
  const value = Math.max(0, age + delta)
  return value < 1 ? `${value.toFixed(1)}초 전` : value < 60 ? `${Math.floor(value)}초 전` : `${Math.floor(value / 60)}분 ${Math.floor(value % 60)}초 전`
}
export function timeText(utc: string | null) {
  if (!utc) return '—'
  const date = new Date(utc)
  const dateFormat = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })
  const time = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(date)
  return dateFormat.format(date) === dateFormat.format(new Date()) ? time : `${dateFormat.format(date)} ${time}`
}
const labels: Record<string, string> = { checking: '연결 확인 중', connected: '연결됨', delayed: '수신 지연', disconnected: '연결 끊김', never_received: '미수신', receiving: '수신 중', unknown: '현재 확인 불가', unconfirmed: '확인 전', moving: '이동 중', stopped: '정지 상태' }
type Tone = 'good' | 'warn' | 'bad' | 'neutral'
function Badge({ status, tone: forced, children }: { status: string; tone?: Tone; children?: ReactNode }) {
  const tone = forced ?? (['connected', 'receiving', 'moving', 'success', 'done'].includes(status) ? 'good' : ['delayed', 'warning'].includes(status) ? 'warn' : ['disconnected', 'failed', 'error'].includes(status) ? 'bad' : 'neutral')
  return <span className={`badge ${tone}`}><span aria-hidden="true">{tone === 'good' ? '●' : tone === 'warn' || tone === 'bad' ? '!' : '○'}</span>{children ?? labels[status]}</span>
}
function Card({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`card ${className}`} aria-label={title}><h2 className="card-heading">{title}</h2>{children}</section>
}
function CommandButton({ command, disabled, busy, onClick, describedBy }: { command: Command; disabled: boolean; busy: boolean; onClick?: () => void; describedBy: string }) {
  return <button className={`command ${command}`} disabled={disabled} aria-busy={busy} aria-describedby={describedBy} onClick={onClick}><span aria-hidden="true">{command === 'pause' ? '■' : '▷'}</span>{busy ? resultLabels[command].pending : commandNames[command]}</button>
}
/** 요청 후 경과 초. 서버 명령은 서버가 잰 값 + 받은 뒤 지난 시간, 화면 자체 결과는 브라우저 시계 */
function requestAge(result: RequestResult, delta: number) {
  return result.age_s != null ? result.age_s + delta : Math.max(0, (Date.now() - Date.parse(result.at)) / 1000)
}
const FOLD_AFTER_S = 60
function ResultBox({ result, delta }: { result: RequestResult; delta: number }) {
  const stageLabels = { waiting: '대기', running: '진행 중', done: '완료', failed: '실패', unknown: '확인 불가' }
  const age = requestAge(result, delta)
  const [open, setOpen] = useState(false)
  if (result.result !== 'pending' && age >= FOLD_AFTER_S && !open) return <div className="result folded" role="status">
    <Badge status={result.result}>{resultLabels[result.command][result.result]}</Badge><span>{ageText(age)}</span><button className="link" onClick={() => setOpen(true)}>자세히</button></div>
  return <div className="result" role="status" aria-busy={result.result === 'pending'}>
    <Badge status={result.result}>{resultLabels[result.command][result.result]}</Badge>
    <p>{result.detail}</p>
    <ol className="steps">{['요청 전송', '로봇 응답', '상태 확인'].map((label, i) => <li key={label}>{label}<strong>{stageLabels[result.stages[i]]}</strong></li>)}</ol>
    <small>요청 시각 {timeText(result.at)} · {ageText(age)}</small>{result.id !== '—' && <small className="request-id">요청 ID {result.id}</small>}
  </div>
}
function Controls({ demo, live, view, delta }: { demo: MockProvider | null; live: LiveControl | null; view: View; delta: number }) {
  const request = demo ? demo.machine.current : live!.current(view)
  const pending = request?.result === 'pending'
  const lock = demo ? demo.lockReason : lockReason(view, request)
  const pause = demo ? demo.pauseReason : pauseReason(view, lock)
  const resume = demo ? demo.resumeReason : resumeReason(view, lock)
  const send = (command: Command) => demo ? demo.request(command) : void live!.send(view, command)
  return <Card title="로봇 제어" className="controls">
    <div className="control-body"><p id="control-reason" role="status" className="muted">{pause || (demo ? '가상 로봇에 제어 요청을 보낼 수 있습니다.' : '순찰을 그 자리에서 멈추거나, 멈춘 곳부터 이어서 순찰합니다.')}</p>
      <CommandButton command="pause" disabled={!!pause} busy={pending && request?.command === 'pause'} describedBy="control-reason" onClick={() => send('pause')} />
      {request?.command === 'pause' && <ResultBox key={request.id} result={request} delta={delta} />}
      <CommandButton command="resume" disabled={!!resume} busy={pending && request?.command === 'resume'} describedBy="resume-reason" onClick={() => send('resume')} />
      <p id="resume-reason" className="muted">{resume || (demo ? '일시 중단된 가상 순찰 작업을 재개합니다.' : '멈춘 지점부터 순찰을 이어서 합니다.')}</p>
      {request?.command === 'resume' && <ResultBox key={request.id} result={request} delta={delta} />}
    </div>
  </Card>
}
const patrolLabels: Record<string, string> = { waiting_localization: '위치 확인 중', patrolling: '순찰 중', pausing: '멈추는 중', paused: '일시정지', completed: '순찰 완료', failed: '순찰 실패' }
const patrolTones: Record<string, Tone> = { patrolling: 'good', pausing: 'warn', paused: 'warn', failed: 'bad' }
/** 순찰 노드가 이동 실패를 사유로 알린 경우 (상태는 그대로 patrolling·paused, docs/CONTROL_SCREEN.md A 4단계 A안) */
export function patrolLabel(state: string, reason: string): { label: string; tone: Tone; note: string } {
  const retry = /^navigation failed, retry (\d+\/\d+)$/.exec(reason)
  if (state === 'patrolling' && retry) return { label: `순찰 중 · 이동 다시 시도 (${retry[1]})`, tone: 'warn', note: '이동이 막혀 잠시 뒤 다시 갑니다.' }
  if (state === 'paused' && reason === 'navigation failed') return { label: '이동 실패 · 확인 후 재개', tone: 'warn', note: '여러 번 다시 가 봐도 막혀서 멈췄습니다. 주변을 확인한 뒤 재개를 눌러 주세요.' }
  return { label: patrolLabels[state] ?? state, tone: patrolTones[state] ?? 'neutral', note: '' }
}
function PatrolCard({ view }: { view: View }) {
  const patrol = view.serverProblem ? null : view.snapshot?.patrol
  const state = patrol?.state
  const old = view.snapshot?.bridge.status !== 'connected'   // 마지막으로 받은 상태일 뿐 지금 상태가 아님
  const target = !patrol || !state ? '' : state === 'completed' ? `${patrol.waypoint_count}개 지점 모두 지남` : `다음 목표 ${patrol.waypoint_name || '—'} (${Math.min(patrol.waypoint_index + 1, patrol.waypoint_count)}/${patrol.waypoint_count})`
  // 받은 적은 있는데 상태가 없음 = 순찰 노드가 꺼졌거나 모르는 상태 (Bridge가 발행자가 없으면 비움)
  const lost = !!patrol && !state && patrol.update_count > 0
  const shown = state ? patrolLabel(state, patrol!.reason) : null
  return <Card title="순찰"><div className="movement patrol-state" role="status">{shown ? <Badge status={state!} tone={old ? 'neutral' : shown.tone}>{shown.label}{old && ' (마지막 상태)'}</Badge> : lost ? <Badge status="lost" tone="warn">순찰 상태 확인 불가</Badge> : <Badge status="unknown">{view.serverProblem ? '현재 확인 불가' : '확인 전'}</Badge>}<span className="patrol-target">{target}</span></div>
    <p className="muted">{!patrol ? '순찰 상태 수신 대기' : old ? '로봇과 연결이 원활하지 않아 지금 상태는 알 수 없습니다' : lost ? '순찰 프로그램이 꺼져 있거나 상태를 알 수 없습니다' : state === 'failed' && patrol.reason ? `사유: ${patrol.reason}` : shown?.note ? shown.note : `마지막 상태 변경 ${timeText(patrol.last_received_at)}`}</p></Card>
}
const FOLLOW_SPAN_M = 10   // 로봇 따라가기: 로봇 중심 가로세로 10 m
function MapCard({ map, view, delta }: { map: MapInfo | null; view: View; delta: number }) {
  const [follow, setFollow] = useState(false)
  const pose = view.snapshot?.pose
  const patrol = view.serverProblem ? null : view.snapshot?.patrol
  const has = !!pose && pose.x != null && pose.y != null && pose.yaw != null
  const stale = view.serverProblem || !pose || pose.stale
  if (!map) return <Card title="지도" className="map-card"><p className="empty">{view.snapshot?.map_available === false ? '서버에 지도가 설정되지 않았습니다' : '지도를 불러오는 중입니다'}</p></Card>
  const points = map.waypoints.map(w => toPixel(map, w.x, w.y))
  const next = patrol?.state && patrol.state !== 'completed' ? patrol.waypoint_index : -1
  const [rx, ry] = has ? toPixel(map, pose!.x!, pose!.y!) : [0, 0]
  const span = FOLLOW_SPAN_M / map.resolution
  const box = follow && has ? [rx - span / 2, ry - span / 2, span, span] : [0, 0, map.width, map.height]
  const unit = Math.max(box[2], box[3]) / 100   // 표시 크기는 보이는 범위 기준 (확대해도 점·글자가 커지지 않게)
  return <Card title="지도" className="map-card">
    <div className="map-frame"><svg viewBox={box.join(' ')} role="img" aria-label="순찰 지도와 로봇 위치">
      {map.image ? <image href={map.image} width={map.width} height={map.height} className="map-image" /> : <rect width={map.width} height={map.height} className="map-blank" />}
      <polyline points={points.map(p => p.join(',')).join(' ')} className="route" strokeWidth={unit * .4} strokeDasharray={`${unit * 1.4} ${unit}`} />
      {map.waypoints.map((w, i) => { const [x, y] = points[i]; const tone = i === next ? 'next' : patrol && i < patrol.waypoint_index ? 'passed' : ''
        return <g key={w.name} className={`waypoint ${tone}`}>{w.type === 'stop' ? <rect x={x - unit * 1.1} y={y - unit * 1.1} width={unit * 2.2} height={unit * 2.2} strokeWidth={unit * .35} /> : <circle cx={x} cy={y} r={unit * 1.1} strokeWidth={unit * .35} />}
          {i === next && <circle cx={x} cy={y} r={unit * 2.4} className="next-ring" strokeWidth={unit * .4} />}<text x={x + unit * 2} y={y - unit * 1.6} fontSize={unit * 3.4}>{w.name}</text></g> })}
      {has && <g className={`robot ${stale ? 'stale' : ''}`} transform={`translate(${rx} ${ry})`}>
        <circle r={Math.max(uncertaintyPx(map, pose!.position_std_m), unit * 2.6)} className="uncertainty" strokeWidth={unit * .25} />
        <g transform={`rotate(${headingDeg(pose!.yaw!)})`}><path d={`M ${unit * 4.4} 0 L ${-unit * 2.7} ${unit * 3} L ${-unit * 1.3} 0 L ${-unit * 2.7} ${-unit * 3} Z`} className="robot-mark" strokeWidth={unit * .3} /></g></g>}
    </svg></div>
    <div className="map-legend"><span role="status">{!has ? '로봇 위치 수신 대기' : stale ? `위치 확인 불가 · 마지막 위치 ${ageText(pose!.age_s, delta)}` : `위치 수신 ${ageText(pose!.age_s, delta)}${pose!.position_std_m != null ? ` · 오차 약 ±${(2 * pose!.position_std_m).toFixed(2)} m` : ''}`}</span>
      <button className="map-toggle" aria-pressed={follow} disabled={!has} onClick={() => setFollow(f => !f)}>{follow ? '전체 지도 보기' : '로봇 따라가기'}</button>
      <span className="legend-keys"><span><i className="key next" />다음 목표</span><span><i className="key stop" />정지 지점</span><span><i className="key pass" />통과 지점</span></span></div>
  </Card>
}
function DemoTools({ demo }: { demo: MockProvider }) {
  const [, redraw] = useState(0)
  const outcomes: Record<Outcome, string> = { success: '성공', reject: '명시적 거절', no_response: '응답 없음', no_confirmation: '응답 후 상태 확인 없음', late: '제한 시간 후 늦은 결과' }
  return <aside className="demo-tools" aria-label="데모 시나리오 도구"><div className="container tools-inner">
    <div><strong>데모 시나리오 도구</strong><small>시나리오 변경·초기화 시 진행 요청과 결과가 지워집니다.</small></div>
    <label>화면 상태<select aria-label="화면 상태" value={demo.scenario} onChange={e => demo.reset(e.target.value as Scenario)}>{Object.entries(scenarios).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>가상 순찰 상태<select aria-label="가상 순찰 상태" value={demo.patrol} onChange={e => demo.setPatrol(e.target.value as Patrol)}><option value="paused">일시 중단 · 재개할 작업 있음</option><option value="patrolling">이미 순찰 중</option><option value="empty">재개할 작업 없음</option><option value="unknown">상태 미확인</option></select></label>
    {(Object.keys(commandNames) as Command[]).map(command => <label key={command}>{commandNames[command]} 결과<select aria-label={`${commandNames[command]} 결과`} value={demo.outcomes[command]} onChange={e => { demo.outcomes[command] = e.target.value as Outcome; redraw(n => n + 1) }}>{Object.entries(outcomes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>)}
    <label>응답 제한 시간(초)<input aria-label="응답 제한 시간(초)" type="number" min="0.1" max="60" step="0.1" defaultValue="5" onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= .1 && n <= 60) demo.machine.responseTimeout = n * 1000 }} /></label>
    <label>상태 확인 제한 시간(초)<input aria-label="상태 확인 제한 시간(초)" type="number" min="0.1" max="60" step="0.1" defaultValue="5" onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= .1 && n <= 60) demo.machine.confirmationTimeout = n * 1000 }} /></label>
    <button onClick={() => demo.reset()}>시나리오 초기화</button><button onClick={() => demo.disconnect()}>진행 중 연결 끊기</button>
  </div></aside>
}
/** 상태 한 줄 요약 (docs/CONTROL_SCREEN.md D): 정상 / 확인 필요 / 연결 끊김 */
export function overall(view: View): { tone: Tone; label: string; detail: string } {
  const state = view.snapshot
  if (view.serverProblem) return { tone: 'bad', label: '연결 끊김', detail: '서버 상태를 갱신할 수 없음' }
  const bridge = state?.bridge.status ?? 'checking'
  if (bridge === 'disconnected') return { tone: 'bad', label: '연결 끊김', detail: '로봇과 연결 끊김' }
  if (bridge === 'checking') return { tone: 'warn', label: '확인 필요', detail: '로봇 연결 확인 중' }
  if (bridge === 'delayed') return { tone: 'warn', label: '확인 필요', detail: '로봇 상태 수신 지연' }
  const late = topicKeys.filter(key => state!.topics[key].status !== 'receiving')
  if (late.length) return { tone: 'warn', label: '확인 필요', detail: late.map(key => `${names[key]} ${state!.topics[key].status === 'never_received' ? '미수신' : '수신 지연'}`).join(', ') }
  return { tone: 'good', label: '정상', detail: '' }
}
function Reception({ state, serverProblem, delta }: { state: Snapshot | null; serverProblem: boolean; delta: number }) {
  return <details className="card reception"><summary className="card-heading">센서 수신 상세<small>개발자용 · 토픽 4개의 수신 상태</small></summary>
    <table><thead><tr><th>항목</th><th>수신 상태</th><th>마지막 수신</th><th>수신 빈도</th></tr></thead>
      <tbody>{topicKeys.map(key => {
        const topic = state?.topics[key]
        const status = serverProblem ? 'unknown' : topic?.status ?? 'never_received'
        const hz = status === 'receiving' ? topic?.receive_hz : null
        return <tr key={key} className={status === 'delayed' ? 'delayed-row' : ''}>
          <th scope="row">{names[key]}</th><td data-label="수신 상태"><span role="status"><Badge status={status} /></span>{status === 'unknown' && <small>{topic?.received_count ? '마지막 수신 이력 보존' : '수신 기록 없음'}</small>}</td>
          <td data-label="마지막 수신"><span>{ageText(topic?.age_s ?? null, delta)}</span><small>{timeText(topic?.last_received_at ?? null)}</small></td>
          <td data-label="수신 빈도">{hz == null ? '—' : `${hz.toFixed(1)} Hz`}{status === 'receiving' && hz == null && <small>측정 중</small>}{status !== 'receiving' && topic?.last_receive_hz != null && <small>마지막 값 {topic.last_receive_hz.toFixed(1)} Hz</small>}</td>
        </tr>
      })}</tbody></table>
    <div className="table-note"><p>수신 상태는 데이터가 들어오는지만 나타냅니다. 센서의 정상 작동 여부를 판단하는 정보는 아닙니다.</p><p>수신 지연 기준 · {state ? topicKeys.map(key => `${names[key]} ${state.settings.topic_delay_s[key]}초`).join(' / ') : '설정 수신 대기'}</p></div>
  </details>
}
function AlertRow({ alert }: { alert: Snapshot['alerts'][number] }) {
  return <li className="alert-row"><time dateTime={alert.at}>{timeText(alert.at)}</time><Badge status={alert.severity}>{{ info: '정보', warning: '주의', error: '오류' }[alert.severity]}</Badge><span>{alert.message}</span>{alert.active && <small>지속 중</small>}</li>
}
export default function App() {
  const [provider] = useState<Provider>(() => location.pathname === '/demo' ? new MockProvider() : new LiveProvider())
  const demo = provider instanceof MockProvider ? provider : null
  const [view, setView] = useState<View>(provider.current)
  const [now, setNow] = useState(performance.now())
  const [, redraw] = useReducer((n: number) => n + 1, 0)
  const [live] = useState(() => demo ? null : new LiveControl(redraw))
  const [map, setMap] = useState<MapInfo | null>(demo ? demoMap : null)
  useEffect(() => { const unsub = provider.subscribe(setView); provider.start(); const timer = setInterval(() => setNow(performance.now()), 200); return () => { clearInterval(timer); unsub(); provider.dispose() } }, [provider])
  const mapAvailable = !!view.snapshot?.map_available
  useEffect(() => {
    if (demo || map || !mapAvailable) return
    const controller = new AbortController()
    fetch('/api/v1/map', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then(value => { if (isMapInfo(value)) setMap(value) }).catch(() => {})
    return () => controller.abort()
  }, [demo, map, mapAvailable])
  const state = view.snapshot
  const summary = overall(view)
  const delta = Math.max(0, (now - view.receivedMono) / 1000)
  const connection = view.serverProblem ? 'unknown' : state?.bridge.status ?? 'checking'
  const motionStatus = view.serverProblem ? 'unknown' : state?.motion.status ?? 'unconfirmed'
  const current = view.serverProblem ? null : state?.motion.current
  const value = current ?? state?.motion.last_valid
  const retained = !!value && !current
  const banner = view.serverProblem ? '서버 상태를 갱신할 수 없습니다. 현재 로봇 연결 상태를 확인할 수 없습니다.' : connection === 'disconnected' ? '로봇과 연결이 끊겼습니다. 아래 정보는 마지막으로 받은 상태입니다.' : connection === 'delayed' ? '로봇 상태가 늦게 오고 있습니다. 지금 상태는 확인할 수 없습니다.' : connection === 'checking' ? '로봇 연결을 확인하고 있습니다. 아직 받은 정보가 없습니다.' : null
  return <>
    {demo && <div className="demo-banner">데모 데이터 · 실제 로봇을 제어하지 않습니다</div>}
    <header><div className="container header-inner"><div className="brand"><h1>LIMBO 관제</h1><span className="robot">{state?.robot_id ?? 'LIMBO-01'}</span>{demo && <span className="mode-tag">데모 데이터</span>}</div><div className="connection"><span role="status" className="overall"><Badge status={summary.label} tone={summary.tone}>{summary.label}</Badge>{summary.detail && <span>{summary.detail}</span>}</span><span className="last-received">로봇 {labels[connection]} · {state?.bridge.last_received_at ? `마지막 수신 ${timeText(state.bridge.last_received_at)} · ${ageText(state.bridge.age_s, delta)}` : '수신 기록 없음'}</span></div></div></header>
    {banner && <div className={`banner ${connection}`} role={connection === 'checking' ? 'status' : 'alert'}><div className="container">{banner}</div></div>}
    {demo && <DemoTools demo={demo} />}
    <main className="container"><div className="page-meta"><span>{demo ? '가상 로봇 상태 및 제어 흐름 검증' : '로봇 상태 모니터링 · 순찰 제어'}</span><a href={demo ? '/' : '/demo'}>{demo ? '실제 수신 화면으로 →' : '가상 제어 데모 보기 →'}</a></div>
      <div className="summary"><PatrolCard view={view} />
        <Card title="이동"><div className="movement" role="status"><Badge status={motionStatus} />{!view.serverProblem && state?.motion.rotating && <span>회전 중</span>}
          <div className={`speed ${retained ? 'muted' : ''}`}><strong>{value ? value.linear_speed_mps.toFixed(2) : '—'}</strong><span>m/s</span>{retained && <Badge status="unknown">마지막 수신 값</Badge>}</div></div>
          <p className="muted">{value ? `주행 정보 ${timeText(value.last_received_at)} 기준 추정값` : '유효한 주행 정보 수신 대기'} · 멈춰 있다고 일시정지가 확인된 것은 아닙니다</p></Card></div>
      <div className="body-grid"><MapCard map={map} view={view} delta={delta} /><Controls demo={demo} live={live} view={view} delta={delta} /></div>
      <Card title="최근 알림" className="alerts">{state?.alerts.length ? <ul>{state.alerts.map(alert => <AlertRow key={alert.id} alert={alert} />)}</ul> : <p className="empty">최근 알림이 없습니다</p>}</Card>
      <Reception state={state} serverProblem={view.serverProblem} delta={delta} />
      <footer>{demo ? '데모의 상태 확인은 가상 이벤트에 기반합니다.' : 'LIMBO-01 · 수신 정보 기반 관제'}<span>표시 시각 Asia/Seoul</span></footer>
    </main>
  </>
}
