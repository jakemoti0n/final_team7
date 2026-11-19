import { useEffect, useState } from 'react'
import type { MapInfo } from '../../map'
import { GuideIcon } from './icons'
import {
  BOUNDS_MARGIN_M, iconLabels, iconNames, inside, limits, mapBounds, nameProblem, nextCategoryKey,
  type Bounds, type Category, type Guide, type IconName,
} from './guide'
import type { Selection } from './GuideCanvas'

/** 오른쪽 칸: 고른 구역·표시점 고치기, 목록, 구역 종류, 그리기 영역 */
export function GuidePanel({ guide, map, selection, onSelect, apply }: {
  guide: Guide; map: MapInfo | null; selection: Selection; onSelect: (s: Selection) => void; apply: (next: Guide | ((g: Guide) => Guide)) => void
}) {
  const byKey = new Map(guide.categories.map(c => [c.key, c]))
  return <div className="guide-panel">
    <SelectedItem guide={guide} selection={selection} onSelect={onSelect} apply={apply} />
    <section aria-label="구역 목록" className="guide-section">
      <h3>구역 <small>{guide.areas.length}개</small></h3>
      {guide.areas.length ? <ul className="guide-list">{guide.areas.map((a, i) => <li key={i}>
        <button type="button" className={selection?.kind === 'area' && selection.index === i ? 'current' : ''} aria-pressed={selection?.kind === 'area' && selection.index === i} onClick={() => onSelect({ kind: 'area', index: i })}>
          <Swatch category={byKey.get(a.category)} /><span>{a.name}</span><small>{byKey.get(a.category)?.label ?? '종류 없음'}</small></button></li>)}</ul>
        : <p className="muted">아직 구역이 없습니다. 위의 「사각형」이나 「다각형」으로 그리세요.</p>}
    </section>
    <section aria-label="표시점 목록" className="guide-section">
      <h3>표시점 <small>{guide.markers.length}개</small></h3>
      {guide.markers.length ? <ul className="guide-list">{guide.markers.map((m, i) => <li key={i}>
        <button type="button" className={selection?.kind === 'marker' && selection.index === i ? 'current' : ''} aria-pressed={selection?.kind === 'marker' && selection.index === i} onClick={() => onSelect({ kind: 'marker', index: i })}>
          <Swatch category={byKey.get(m.category)} /><span>{m.name}</span><small>{byKey.get(m.category)?.label ?? '종류 없음'}</small></button></li>)}</ul>
        : <p className="muted">입구·안내데스크처럼 점으로 표시할 곳은 「표시점」으로 찍으세요.</p>}
    </section>
    <Categories guide={guide} apply={apply} />
    <BoundsEditor guide={guide} map={map} apply={apply} />
  </div>
}

export function Swatch({ category }: { category?: Category }) {
  return <span className="guide-swatch" style={{ background: category?.color ?? '#FFFFFF' }} aria-hidden="true">{category && <GuideIcon icon={category.icon} />}</span>
}

function SelectedItem({ guide, selection, onSelect, apply }: { guide: Guide; selection: Selection; onSelect: (s: Selection) => void; apply: (next: Guide | ((g: Guide) => Guide)) => void }) {
  const item = selection?.kind === 'area' ? guide.areas[selection.index] : selection?.kind === 'marker' ? guide.markers[selection.index] : undefined
  const [name, setName] = useState(item?.name ?? '')
  useEffect(() => { setName(item?.name ?? '') }, [selection?.kind, selection?.index, item?.name])
  if (!selection || !item) return <section className="guide-section guide-selected" aria-label="고른 항목"><h3>고른 항목</h3><p className="muted">지도에서 구역이나 표시점을 누르면 여기서 이름과 종류를 바꿀 수 있습니다.</p></section>
  const kind = selection.kind === 'area' ? '구역' : '표시점'
  const problem = nameProblem(name)
  const update = (patch: { name?: string; category?: string }) => apply(g => selection.kind === 'area'
    ? { ...g, areas: g.areas.map((a, i) => i === selection.index ? { ...a, ...patch } : a) }
    : { ...g, markers: g.markers.map((m, i) => i === selection.index ? { ...m, ...patch } : m) })
  const saveName = () => { if (!problem && name.trim() !== item.name) update({ name: name.trim() }) }
  return <section className="guide-section guide-selected" aria-label="고른 항목">
    <h3>고른 {kind}</h3>
    <label>이름<input aria-label="이름" value={name} maxLength={limits.name} onChange={e => setName(e.target.value)} onBlur={saveName} onKeyDown={e => { if (e.key === 'Enter') saveName(); if (e.key === 'Escape') setName(item.name) }} aria-invalid={!!problem} /></label>
    {problem && <small className="guide-error">{problem}</small>}
    <label>종류<select aria-label="종류" value={item.category} onChange={e => update({ category: e.target.value })}>{guide.categories.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
    <small className="muted">{selection.kind === 'area'
      ? `꼭짓점 ${(item as Guide['areas'][number]).polygon.length}개 · ●를 끌면 모양, ○를 끌면 꼭짓점 추가 · 화살표 키로 0.25 m씩 이동`
      : `위치 ${(item as Guide['markers'][number]).x.toFixed(2)}, ${(item as Guide['markers'][number]).y.toFixed(2)} m · 끌거나 화살표 키로 이동`}</small>
    <div className="guide-row">
      <button type="button" className="danger" onClick={() => { apply(g => selection.kind === 'area' ? { ...g, areas: g.areas.filter((_, i) => i !== selection.index) } : { ...g, markers: g.markers.filter((_, i) => i !== selection.index) }); onSelect(null) }}>{kind} 삭제</button>
      <button type="button" onClick={() => onSelect(null)}>선택 해제</button>
    </div>
  </section>
}

function Categories({ guide, apply }: { guide: Guide; apply: (next: Guide | ((g: Guide) => Guide)) => void }) {
  const used = new Set([...guide.areas.map(a => a.category), ...guide.markers.map(m => m.category)])
  const change = (key: string, patch: Partial<Category>) => apply(g => ({ ...g, categories: g.categories.map(c => c.key === key ? { ...c, ...patch } : c) }))
  return <section aria-label="구역 종류" className="guide-section">
    <h3>구역 종류 <small>{guide.categories.length}개</small></h3>
    <p className="muted">색·이름·아이콘은 방문자 화면에 그대로 보입니다. 쓰고 있는 종류는 지울 수 없습니다.</p>
    <ul className="guide-categories">{guide.categories.map(c => <li key={c.key} data-testid="guide-category">
      <input type="color" value={c.color.toLowerCase()} aria-label={`${c.label} 색`} onChange={e => change(c.key, { color: e.target.value.toUpperCase() })} />
      <CategoryLabel category={c} onChange={label => change(c.key, { label })} />
      <span className="guide-icon-pick"><GuideIcon icon={c.icon} /><select value={c.icon} aria-label={`${c.label} 아이콘`} onChange={e => change(c.key, { icon: e.target.value as IconName })}>{iconNames.map(n => <option key={n} value={n}>{iconLabels[n]}</option>)}</select></span>
      <button type="button" className="icon-button" disabled={used.has(c.key) || guide.categories.length === 1} title={used.has(c.key) ? '쓰고 있는 종류는 지울 수 없습니다' : '종류 삭제'} aria-label={`${c.label} 종류 삭제`}
        onClick={() => apply(g => ({ ...g, categories: g.categories.filter(x => x.key !== c.key) }))}>✕</button>
    </li>)}</ul>
    <button type="button" className="guide-add" disabled={guide.categories.length >= limits.categories}
      onClick={() => apply(g => ({ ...g, categories: [...g.categories, { key: nextCategoryKey(g.categories), label: `새 종류 ${g.categories.length + 1}`, color: '#EEF2F7', icon: 'none' }] }))}>+ 종류 추가</button>
  </section>
}

function CategoryLabel({ category, onChange }: { category: Category; onChange: (label: string) => void }) {
  const [value, setValue] = useState(category.label)
  useEffect(() => { setValue(category.label) }, [category.label])
  const problem = nameProblem(value)
  const save = () => { if (!problem && value.trim() !== category.label) onChange(value.trim()); else if (problem) setValue(category.label) }
  return <input className="guide-category-label" value={value} maxLength={limits.name} aria-label={`${category.label} 이름`} aria-invalid={!!problem}
    onChange={e => setValue(e.target.value)} onBlur={save} onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setValue(category.label) }} />
}

function BoundsEditor({ guide, map, apply }: { guide: Guide; map: MapInfo | null; apply: (next: Guide | ((g: Guide) => Guide)) => void }) {
  const [draft, setDraft] = useState<Bounds>(guide.bounds)
  const [message, setMessage] = useState('')
  useEffect(() => { setDraft(guide.bounds) }, [guide.bounds])
  const set = (next: Bounds) => {
    const points = [...guide.areas.flatMap(a => a.polygon), ...guide.markers.map(m => [m.x, m.y] as [number, number])]
    if (!(next.x_max > next.x_min && next.y_max > next.y_min) || next.x_max - next.x_min > limits.span || next.y_max - next.y_min > limits.span) { setMessage(`크기가 0보다 크고 ${limits.span} m 이하여야 합니다.`); return }
    if (!points.every(p => inside(p, next))) { setMessage('이미 그린 구역·표시점이 영역 밖으로 나갑니다. 먼저 옮기거나 지우세요.'); return }
    setMessage(''); apply(g => ({ ...g, bounds: next }))
  }
  const field = (key: keyof Bounds, label: string) => <label>{label}<input type="number" step="0.5" value={draft[key]} onChange={e => setDraft({ ...draft, [key]: Number(e.target.value) })} /></label>
  return <section aria-label="그리기 영역" className="guide-section">
    <h3>그리기 영역</h3>
    <p className="muted">약도를 그릴 수 있는 범위(m). 지도보다 넓혀서 로봇이 가지 않는 방도 그릴 수 있습니다. 점선 상자가 실제 지도 범위입니다.</p>
    <div className="guide-bounds">{field('x_min', 'x 최소')}{field('x_max', 'x 최대')}{field('y_min', 'y 최소')}{field('y_max', 'y 최대')}</div>
    <div className="guide-row">
      <button type="button" onClick={() => set(draft)}>영역 적용</button>
      {map && <button type="button" onClick={() => set(mapBounds(map, BOUNDS_MARGIN_M))}>지도 + 사방 {BOUNDS_MARGIN_M} m</button>}
    </div>
    {message && <small className="guide-error" role="status">{message}</small>}
  </section>
}
