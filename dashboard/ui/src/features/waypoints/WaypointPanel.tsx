import { useEffect, useState } from 'react'
import type { MockProvider } from '../../demo'
import type { MapInfo, Waypoint } from '../../map'

export const waypointLockHint = '주행 완료 후 변경 가능합니다'
export type WaypointMode = { kind: 'add' } | { kind: 'move'; index: number }
export type WaypointDocument = { revision: string; waypoints: Waypoint[]; file: string; applies: string }
export type WaypointChange = { action: 'add'; waypoint: Waypoint } | { action: 'move'; name: string; x: number; y: number } | { action: 'delete'; name: string } | { action: 'rename'; name: string; new_name: string } | { action: 'reorder'; order: string[] }
export function WaypointPanel({ demo, map, document, problem, locked, onChange, mode, picked, setMode, setPicked }: {
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
      <span className="waypoint-row-main"><span className="waypoint-name" data-testid="waypoint-name"><strong>{w.name}</strong><small data-testid="waypoint-coords">{w.type === 'stop' ? '정지' : '통과'} · {w.x.toFixed(2)}, {w.y.toFixed(2)} m</small></span></span>
      <span className="waypoint-actions"><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document)} onClick={() => { setMode(null); setPicked(null); setRenameIndex(i); setRenameDraft(w.name); setMessage('') }}>이름 변경</button></span><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document)} onClick={() => begin({ kind: 'move', index: i })}>위치 교체</button></span><span title={locked ? waypointLockHint : undefined}><button type="button" disabled={locked || busy || (!demo && !document) || (!demo && (waypoints.length === 1 || i === waypoints.length - 1))} onClick={() => void apply({ action: 'delete', name: w.name }, `${w.name} 지점을 삭제해`)}>삭제</button></span></span><span className="waypoint-drag-wrap" title={locked ? waypointLockHint : '끌어서 순서 변경'}><button className="waypoint-drag" type="button" draggable={!locked && !busy && (demo !== null || document !== null)} disabled={locked || busy || (!demo && !document)} aria-label={`${w.name} 순서 끌어서 변경`} title="끌어서 순서 변경" onDragStart={event => { setDragIndex(i); event.dataTransfer.setData('text/plain', w.name); event.dataTransfer.effectAllowed = 'move' }} onDragEnd={() => { setDragIndex(null); setOverIndex(null) }}>⋮⋮</button></span>
      {renameIndex === i && !locked && <div className="waypoint-rename"><label>새 이름<input value={renameDraft} maxLength={32} onChange={event => setRenameDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') saveName(); if (event.key === 'Escape') setRenameIndex(null) }} /></label><button type="button" disabled={locked || busy} onClick={saveName}>저장</button><button type="button" disabled={busy} onClick={() => setRenameIndex(null)}>취소</button></div>}
    </li>)}</ol> : <p className="muted">저장된 지점이 없습니다.</p>}
    <small>순서를 바꾸려면 ⋮⋮ 표시를 다른 지점으로 끌어 놓으세요.</small>
    <span data-testid="waypoint-add-wrap" title={locked ? waypointLockHint : undefined}><button className="waypoint-add" type="button" disabled={locked || busy || !map || (!demo && !document)} onClick={() => begin({ kind: 'add' })}>+ 새 지점 만들기</button></span>
    {mode && !locked && <div className="waypoint-editor"><p>{mode.kind === 'add' ? '새 지점의 이름과 종류를 정하고 지도에서 위치를 선택하세요. 통과 지점은 마지막 정지 지점 앞에 들어갑니다.' : `${waypoints[mode.index]?.name ?? '지점'}의 새 위치를 지도에서 선택하세요.`}</p>
      {mode.kind === 'add' && <div className="waypoint-fields"><label>이름<input value={name} maxLength={32} onChange={e => setName(e.target.value)} /></label><label>종류<select value={type} onChange={e => setType(e.target.value as 'pass' | 'stop')}><option value="stop">정지</option><option value="pass">통과</option></select></label></div>}
      <p role="status">{picked ? `선택한 위치: ${picked[0].toFixed(2)}, ${picked[1].toFixed(2)} m` : '지도에서 위치를 클릭하세요.'}</p>
      <div className="waypoint-actions"><button type="button" disabled={locked || !picked || busy} onClick={save}>{busy ? '저장 중…' : '저장'}</button><button type="button" disabled={busy} onClick={() => { setMode(null); setPicked(null) }}>취소</button></div></div>}
    {message && <p className="waypoint-message" role="status">{message}</p>}
    {!demo && <small>마지막 정지 지점은 삭제할 수 없습니다. 다른 정지 지점을 추가한 뒤 삭제하세요.</small>}
  </section>
}
