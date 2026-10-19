import { useEffect, useReducer, useState, type ReactNode } from 'react'
import { LiveProvider } from './live'
import { MockProvider, demoMap, scenarios, type Patrol, type Scenario } from './demo'
import { commandNames, resultLabels, type Command, type Outcome, type RequestResult } from './commands'
import { LiveControl, driveControl } from './control'
import { fromPixel, headingDeg, isMapInfo, toPixel, uncertaintyPx, type MapInfo, type Waypoint } from './map'
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
const waypointLocked = (view: View) => ['waiting_localization', 'patrolling', 'pausing', 'paused'].includes(view.snapshot?.patrol?.state ?? '')
const waypointLockHint = '주행 완료 후 변경 가능합니다'
type WaypointMode = { kind: 'add' } | { kind: 'move'; index: number }
type WaypointDocument = { revision: string; waypoints: Waypoint[]; file: string; applies: string }
type WaypointChange = { action: 'add'; waypoint: Waypoint } | { action: 'move'; name: string; x: number; y: number } | { action: 'delete'; name: string } | { action: 'rename'; name: string; new_name: string } | { action: 'reorder'; order: string[] }
function WaypointPanel({ demo, map, document, problem, locked, onChange, mode, picked, setMode, setPicked }: {
  demo: MockProvider | null; map: MapInfo | null; document: WaypointDocument | null; problem: string | null; locked: boolean
  onChange: (change: WaypointChange) => Promise<void>; mode: WaypointMode | null; picked: [number, number] | null
  setMode: (mode: WaypointMode | null) => void; setPicked: (point: [number, number] | null) => void
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState<'pass' | 'stop'>('stop')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [renameIndex, setRenameIndex] = useState<number | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const waypoints = map?.waypoints ?? []
  useEffect(() => { if (locked) { setMode(null); setPicked(null); setRenameIndex(null); setDragIndex(null); setOverIndex(null) } }, [locked, setMode, setPicked])
  const begin = (next: WaypointMode) => { setRenameIndex(null); setMode(next); setPicked(null); setMessage(''); if (next.kind === 'add') { setName(`WP-${waypoints.length + 1}`); setType('stop') } }
  const apply = async (change: WaypointChange, success: string) => {
    if (locked) { setMessage(waypointLockHint); return }
    setBusy(true); setMessage('')
    try {
      if (demo) {
        const updated = change.action === 'add' ? [...waypoints, change.waypoint]
          : change.action === 'move' ? waypoints.map(w => w.name === change.name ? { ...w, x: change.x, y: change.y } : w)
            : change.action === 'delete' ? waypoints.filter(w => w.name !== change.name)
              : change.action === 'rename' ? waypoints.map(w => w.name === change.name ? { ...w, name: change.new_name } : w)
                : change.order.map(name => waypoints.find(w => w.name === name)!)
        demo.setWaypoints(updated)
      } else await onChange(change)
      setMode(null); setPicked(null); setRenameIndex(null); setMessage(`${success}${demo ? ' 데모 경로에 반영했습니다.' : ' 저장했습니다. 순찰 노드를 다시 시작하면 적용됩니다.'}`)
    } catch (err) { setMessage(err instanceof Error ? err.message : 'Waypoint 변경에 실패했습니다.') }
    finally { setBusy(false) }
  }
  const save = () => {
    if (!mode || !picked) return
    const [x, y] = picked
    if (mode.kind === 'add') {
      const label = name.trim()
      if (!label || label.length > 32 || waypoints.some(w => w.name.toLowerCase() === label.toLowerCase())) {
        setMessage('이름은 1~32자이며 기존 지점과 달라야 합니다.'); return
      }
      void apply({ action: 'add', waypoint: { name: label, type, x, y } }, `${label} 지점을`)
    } else {
      const target = waypoints[mode.index]
      if (target) void apply({ action: 'move', name: target.name, x, y }, `${target.name} 지점의 위치를`)
    }
  }
  const saveName = () => {
    if (renameIndex === null) return
    const target = waypoints[renameIndex]
    const next = renameDraft.trim()
    if (!target) return
    if (!next || next.length > 32 || waypoints.some((w, i) => i !== renameIndex && w.name.toLowerCase() === next.toLowerCase())) {
      setMessage('이름은 1~32자이며 기존 지점과 달라야 합니다.'); return
    }
    if (next === target.name) { setRenameIndex(null); return }
    void apply({ action: 'rename', name: target.name, new_name: next }, `${target.name} 지점의 이름을 ${next}(으)로 변경해`)
  }
  const dropAt = (index: number) => {
    if (dragIndex === null || locked || busy || (!demo && !document)) return
    const from = dragIndex
    setDragIndex(null); setOverIndex(null)
    if (from === index) return
    const updated = [...waypoints]
    const [moved] = updated.splice(from, 1)
    updated.splice(index, 0, moved)
    if (updated[updated.length - 1].type !== 'stop') {
      setMessage('마지막 지점은 정지 지점이어야 합니다.'); return
    }
    void apply({ action: 'reorder', order: updated.map(w => w.name) }, `${moved.name} 지점의 순서를 변경해`)
  }
  return <section className="waypoint-panel" aria-label="Waypoint 목록" title={locked ? waypointLockHint : undefined}>
    <div className="waypoint-heading"><strong>Waypoint 목록</strong><span>{waypoints.length}개</span></div>
    <p className="muted">{demo ? '데모 경로입니다. 변경 내용은 새로고침하면 초기화됩니다.' : document ? `${document.file}에 저장됩니다. 변경된 경로는 다음 순찰 시작 시 적용됩니다.` : problem || 'Waypoint 설정을 불러오는 중입니다.'}</p>
    {waypoints.length ? <ol className="waypoint-list">{waypoints.map((w, i) => <li key={w.name} className={overIndex === i && dragIndex !== i ? 'drag-over' : ''} onDragOver={event => { if (dragIndex !== null && !locked && !busy) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setOverIndex(i) } }} onDragLeave={() => { if (overIndex === i) setOverIndex(null) }} onDrop={event => { event.preventDefault(); dropAt(i) }}>
      <span className="waypoint-row-main"><span className="waypoint-name"><strong>{w.name}</strong><small>{w.type === 'stop' ? '정지' : '통과'} · {w.x.toFixed(2)}, {w.y.toFixed(2)} m</small></span></span>
      <span className="waypoint-actions"><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document)} onClick={() => { setMode(null); setPicked(null); setRenameIndex(i); setRenameDraft(w.name); setMessage('') }}>이름 변경</button></span><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document)} onClick={() => begin({ kind: 'move', index: i })}>위치 교체</button></span><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document) || (!demo && (waypoints.length === 1 || i === waypoints.length - 1))} onClick={() => void apply({ action: 'delete', name: w.name }, `${w.name} 지점을 삭제해`)}>삭제</button></span></span><span className="waypoint-drag-wrap" title={locked ? waypointLockHint : '끌어서 순서 변경'}><button className="waypoint-drag" type="button" draggable={!locked && !busy && (demo !== null || document !== null)} disabled={locked || busy || (!demo && !document)} aria-label={`${w.name} 순서 끌어서 변경`} title="끌어서 순서 변경" onDragStart={event => { setDragIndex(i); event.dataTransfer.setData('text/plain', w.name); event.dataTransfer.effectAllowed = 'move' }} onDragEnd={() => { setDragIndex(null); setOverIndex(null) }}>⋮⋮</button></span>
      {renameIndex === i && !locked && <div className="waypoint-rename"><label>새 이름<input value={renameDraft} maxLength={32} onChange={event => setRenameDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') saveName(); if (event.key === 'Escape') setRenameIndex(null) }} /></label><button type="button" disabled={locked || busy} onClick={saveName}>저장</button><button type="button" disabled={busy} onClick={() => setRenameIndex(null)}>취소</button></div>}
    </li>)}</ol> : <p className="muted">저장된 지점이 없습니다.</p>}
    <small>순서를 바꾸려면 ⋮⋮ 표시를 다른 지점으로 끌어 놓으세요.</small>
    <span title={locked ? waypointLockHint : undefined}><button className="waypoint-add" type="button" disabled={locked || busy || !map || (!demo && !document)} onClick={() => begin({ kind: 'add' })}>+ 새 지점 만들기</button></span>
    {mode && !locked && <div className="waypoint-editor"><p>{mode.kind === 'add' ? '새 지점의 이름과 종류를 정하고 지도에서 위치를 선택하세요. 통과 지점은 마지막 정지 지점 앞에 들어갑니다.' : `${waypoints[mode.index]?.name ?? '지점'}의 새 위치를 지도에서 선택하세요.`}</p>
      {mode.kind === 'add' && <div className="waypoint-fields"><label>이름<input value={name} maxLength={32} onChange={e => setName(e.target.value)} /></label><label>종류<select value={type} onChange={e => setType(e.target.value as 'pass' | 'stop')}><option value="stop">정지</option><option value="pass">통과</option></select></label></div>}
      <p role="status">{picked ? `선택한 위치: ${picked[0].toFixed(2)}, ${picked[1].toFixed(2)} m` : '지도에서 위치를 클릭하세요.'}</p>
      <div className="waypoint-actions"><button type="button" disabled={locked || !picked || busy} onClick={save}>{busy ? '저장 중…' : '저장'}</button><button type="button" disabled={busy} onClick={() => { setMode(null); setPicked(null) }}>취소</button></div></div>}
    {message && <p className="waypoint-message" role="status">{message}</p>}
    {!demo && <small>마지막 정지 지점은 삭제할 수 없습니다. 다른 정지 지점을 추가한 뒤 삭제하세요.</small>}
  </section>
}
function Controls({ demo, live, view, delta, map, waypointDocument, waypointProblem, changeWaypoint, waypointMode, picked, setWaypointMode, setPicked }: { demo: MockProvider | null; live: LiveControl | null; view: View; delta: number; map: MapInfo | null; waypointDocument: WaypointDocument | null; waypointProblem: string | null; changeWaypoint: (change: WaypointChange) => Promise<void>; waypointMode: WaypointMode | null; picked: [number, number] | null; setWaypointMode: (mode: WaypointMode | null) => void; setPicked: (point: [number, number] | null) => void }) {
  const request = demo ? demo.machine.current : live!.current(view)
  const [starting, setStarting] = useState<'idle' | 'launching' | 'waiting' | 'started' | 'failed'>('idle')
  const [startMessage, setStartMessage] = useState('')
  const [startLog, setStartLog] = useState('')
  const [startPatrolCount, setStartPatrolCount] = useState(0)
  const [launchStatus, setLaunchStatus] = useState<'idle' | 'running' | 'exited' | 'stopping'>('idle')
  const [stopping, setStopping] = useState(false)
  const [stopMessage, setStopMessage] = useState('')
  const patrolExited = !demo && launchStatus === 'exited'
  const { action, reason } = driveControl(view, request, patrolExited || starting === 'launching' || starting === 'waiting')
  const active = !patrolExited && waypointLocked(view)
  useEffect(() => {
    if (starting === 'waiting' && active && (view.snapshot?.patrol?.update_count ?? 0) > startPatrolCount) { setStarting('started'); setStartMessage('순찰 노드의 상태를 수신했습니다.') }
  }, [active, starting, startPatrolCount, view.snapshot?.patrol?.update_count])
  useEffect(() => {
    if (starting !== 'waiting' || demo) return
    let done = false
    let attempts = 0
    const timer = setInterval(async () => {
      if (done) return
      attempts++
      const status = await fetch('/api/v1/patrol/launch').then(r => r.ok ? r.json() : null).catch(() => null)
      if (done) return
      if (status?.status === 'exited') {
        setStarting('failed')
        setStartMessage(`순찰 노드가 종료되었습니다${status.exit_code == null ? '' : ` (종료 코드 ${status.exit_code})`}. 로그: ${status.log || startLog}`)
      } else if (attempts >= 30) {
        setStarting('failed')
        setStartMessage(`순찰 시작 상태를 확인하지 못했습니다. 로그: ${startLog}`)
      }
    }, 1000)
    return () => { done = true; clearInterval(timer) }
  }, [starting, demo, startLog])
  const start = async () => {
    if (demo) { demo.startPatrol(); setStarting('started'); setStartMessage('데모 순찰을 시작했습니다.'); return }
    setStartPatrolCount(view.snapshot?.patrol?.update_count ?? 0)
    setStopMessage('')
    setStarting('launching'); setStartMessage('순찰 노드를 시작하고 있습니다.')
    try {
      const response = await fetch('/api/v1/patrol/start', { method: 'POST', signal: AbortSignal.timeout(5000) })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(({ bridge_not_connected: 'Bridge 연결을 확인한 뒤 시작하세요.', patrol_already_running: '이미 순찰 노드가 실행 중입니다.', patrol_state_unavailable: '순찰 상태를 확인할 수 없습니다.', ros_domain_not_configured: 'Dashboard의 ROS_DOMAIN_ID 설정이 필요합니다.' } as Record<string, string>)[body?.error?.code] || body?.error?.message || `시작 요청 실패 (${response.status})`)
      setStartLog(body?.log || '')
      setLaunchStatus('running')
      setStarting('waiting'); setStartMessage('순찰 노드를 실행했습니다. 상태 보고를 기다립니다.')
    } catch (err) { setStarting('failed'); setStartMessage(err instanceof Error ? err.message : '순찰 시작 요청에 실패했습니다.') }
  }
  useEffect(() => {
    if (demo) return
    let cancelled = false
    const refresh = async () => {
      const status = await fetch('/api/v1/patrol/launch').then(r => r.ok ? r.json() : null).catch(() => null)
      if (!cancelled && status?.status) setLaunchStatus(current => current === 'stopping' && status.status === 'running' ? current : status.status)
    }
    void refresh()
    const timer = setInterval(() => void refresh(), 2000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [demo])
  const stop = async () => {
    if (demo) { demo.stopPatrol(); setStopMessage('데모 순찰을 종료했습니다.'); return }
    setStopping(true); setStopMessage('순찰 노드를 종료하고 있습니다.')
    try {
      const response = await fetch('/api/v1/patrol/stop', { method: 'POST', signal: AbortSignal.timeout(5000) })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.error?.code === 'patrol_not_running' ? 'Dashboard가 시작한 순찰 노드가 실행 중이지 않습니다.' : body?.error?.message || `종료 요청 실패 (${response.status})`)
      setLaunchStatus('stopping')
      setStarting('idle'); setStartMessage('')
      setStopMessage('순찰 노드에 종료 신호를 보냈습니다.')
    } catch (err) { setStopMessage(err instanceof Error ? err.message : '순찰 종료 요청에 실패했습니다.') }
    finally { setStopping(false) }
  }
  useEffect(() => {
    if (launchStatus === 'exited' && stopMessage === '순찰 노드에 종료 신호를 보냈습니다.')
      setStopMessage('순찰 노드가 종료되었습니다. 다시 시작할 수 있습니다.')
  }, [launchStatus, stopMessage])
  const busy = request?.result === 'pending' || starting === 'launching' || starting === 'waiting'
  const disabled = !!reason || busy || (!demo && launchStatus === 'stopping')
  const label = action === 'start' ? '주행 시작' : action === 'pause' ? '주행 정지' : '주행 재개'
  const send = () => { if (action === 'start') void start(); else { setStartMessage(''); if (demo) demo.request(action); else void live!.send(view, action) } }
  return <Card title="로봇 제어" className="controls">
    <div className="control-body"><p id="control-reason" role="status" className="muted">{reason || (action === 'start' ? '저장된 waypoint 경로로 새 순찰을 시작합니다.' : action === 'pause' ? '현재 순찰을 일시정지합니다.' : '멈춘 지점부터 순찰을 이어서 합니다.')}</p>
      <button className={`command ${action === 'pause' ? 'pause' : 'resume'}`} disabled={disabled} aria-busy={busy} aria-describedby="control-reason" onClick={send}><span aria-hidden="true">{action === 'pause' ? '■' : '▷'}</span>{busy ? action === 'start' ? '주행 시작 중' : action === 'pause' ? '정지 요청 중' : '재개 요청 중' : label}</button>
      <button className="patrol-stop" type="button" disabled={stopping || (demo ? !active : launchStatus !== 'running')} onClick={() => void stop()}>{stopping ? '순찰 종료 중' : '순찰 종료'}</button>
      {stopMessage && <p className="muted" role="status">{stopMessage}</p>}
      {request && <ResultBox key={request.id} result={request} delta={delta} />}
      {startMessage && <p className="muted" role="status">{startMessage}</p>}
      <WaypointPanel demo={demo} map={map} document={waypointDocument} locked={active || launchStatus === 'running' || launchStatus === 'stopping' || starting === 'launching' || starting === 'waiting' || stopping} problem={waypointProblem} onChange={changeWaypoint} mode={waypointMode} picked={picked} setMode={setWaypointMode} setPicked={setPicked} />
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
function MapCard({ map, view, delta, onPick }: { map: MapInfo | null; view: View; delta: number; onPick?: (point: [number, number]) => void }) {
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
    <div className={`map-frame ${onPick ? 'editing' : ''}`}><svg viewBox={box.join(' ')} role="img" aria-label="순찰 지도와 로봇 위치" onClick={event => {
      if (!onPick) return
      const svg = event.currentTarget, matrix = svg.getScreenCTM()
      if (!matrix) return
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
      if (point.x < 0 || point.x > map.width || point.y < 0 || point.y > map.height) return
      onPick(fromPixel(map, point.x, point.y))
    }}>
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
      {onPick && <span className="map-pick-hint">지도에서 지점 위치를 클릭하세요</span>}
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
  const [liveMap, setLiveMap] = useState<MapInfo | null>(null)
  const [waypointDocument, setWaypointDocument] = useState<WaypointDocument | null>(null)
  const [waypointProblem, setWaypointProblem] = useState<string | null>(null)
  const [waypointMode, setWaypointMode] = useState<WaypointMode | null>(null)
  const [picked, setPicked] = useState<[number, number] | null>(null)
  const map = demo ? { ...demoMap, waypoints: demo.waypoints } : liveMap
  useEffect(() => { const unsub = provider.subscribe(setView); provider.start(); const timer = setInterval(() => setNow(performance.now()), 200); return () => { clearInterval(timer); unsub(); provider.dispose() } }, [provider])
  const mapAvailable = !!view.snapshot?.map_available
  useEffect(() => {
    if (demo || liveMap || !mapAvailable) return
    const controller = new AbortController()
    fetch('/api/v1/map', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then(value => { if (isMapInfo(value)) setLiveMap(value) }).catch(() => {})
    return () => controller.abort()
  }, [demo, liveMap, mapAvailable])
  useEffect(() => {
    if (demo || !liveMap) return
    const controller = new AbortController()
    fetch('/api/v1/waypoints', { signal: controller.signal }).then(r => { if (!r.ok) throw new Error(r.status === 404 ? 'Waypoint API를 사용할 수 없습니다. Dashboard 서버를 다시 시작하고 설정을 확인하세요.' : 'Waypoint 목록을 읽지 못했습니다.'); return r.json() }).then(value => {
      if (value && Array.isArray(value.waypoints) && typeof value.revision === 'string') {
        setWaypointDocument(value)
        setWaypointProblem(null)
        setLiveMap(current => current ? { ...current, waypoints: value.waypoints } : current)
      }
    }).catch(err => { if (!controller.signal.aborted) setWaypointProblem(err instanceof Error ? err.message : 'Waypoint 목록을 읽지 못했습니다.') })
    return () => controller.abort()
  }, [demo, !!liveMap])
  const changeWaypoint = async (change: WaypointChange) => {
    if (!waypointDocument) throw new Error('Waypoint 설정을 불러오지 못했습니다.')
    let response: Response
    try {
      response = await fetch('/api/v1/waypoints', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: waypointDocument.revision, ...change }) })
    } catch { throw new Error('서버에 연결할 수 없습니다.') }
    if (!response.ok) {
      if (response.status === 409) {
        const latest = await fetch('/api/v1/waypoints').then(r => r.ok ? r.json() : null).catch(() => null)
        if (latest) { setWaypointDocument(latest); setLiveMap(current => current ? { ...current, waypoints: latest.waypoints } : current) }
      }
      const body = await response.json().catch(() => null)
      throw new Error(body?.error?.code === 'patrol_active' ? waypointLockHint : body?.error?.code === 'revision_conflict' ? '다른 곳에서 경로가 변경되어 목록을 새로 불러왔습니다. 확인 후 다시 시도하세요.' : body?.error?.message || 'Waypoint 변경에 실패했습니다.')
    }
    const updated: WaypointDocument = await response.json()
    setWaypointDocument(updated)
    setLiveMap(current => current ? { ...current, waypoints: updated.waypoints } : current)
  }
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
      <div className="body-grid"><MapCard map={map} view={view} delta={delta} onPick={waypointMode ? setPicked : undefined} /><Controls demo={demo} live={live} view={view} delta={delta} map={map} waypointDocument={waypointDocument} waypointProblem={waypointProblem} changeWaypoint={changeWaypoint} waypointMode={waypointMode} picked={picked} setWaypointMode={setWaypointMode} setPicked={setPicked} /></div>
      <Card title="최근 알림" className="alerts">{state?.alerts.length ? <ul>{state.alerts.map(alert => <AlertRow key={alert.id} alert={alert} />)}</ul> : <p className="empty">최근 알림이 없습니다</p>}</Card>
      <Reception state={state} serverProblem={view.serverProblem} delta={delta} />
      <footer>{demo ? '데모의 상태 확인은 가상 이벤트에 기반합니다.' : 'LIMBO-01 · 수신 정보 기반 관제'}<span>표시 시각 Asia/Seoul</span></footer>
    </main>
  </>
}
