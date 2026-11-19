import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { MapInfo, Waypoint } from '../../map'
import { GuideDrawing } from './GuideDrawing'
import {
  bbox, clampPoint, contentBox, FINE_SNAP_M, inside, rectangle, simplePolygon, snapPoint, svgY, viewBoxAround, viewBoxOf, nextName,
  type Bounds, type Guide, type Point,
} from './guide'

export type Tool = 'select' | 'rect' | 'polygon' | 'marker'
export type Selection = { kind: 'area' | 'marker'; index: number } | null
export type Background = 'sketch' | 'original' | 'none'

type Gesture =
  | { kind: 'pan'; startX: number; startY: number; box: number[] }
  | { kind: 'move-area'; index: number; start: Point; before: Guide; last: Point }
  | { kind: 'move-marker'; index: number; before: Guide }
  | { kind: 'vertex'; index: number; vertex: number; before: Guide }
  | { kind: 'rect'; start: Point; end: Point }

/**
 * 약도 그리기 판. 좌표는 미터(y 뒤집음). 지도 그림을 지도 범위에 깔고, 그 위에 구역·표시점을 그린다.
 * 선택 도구: 구역·표시점을 누르면 고르고, 끌면 옮긴다. 꼭짓점(●)을 끌면 모양을, 변 가운데(○)를 끌면 꼭짓점을 더한다.
 * 빈 곳을 끌면 화면 이동, 휠은 확대·축소. 좌표는 0.25 m 격자에 맞추고 Alt를 누르면 5 cm.
 */
export function GuideCanvas({ guide, map, background, opacity, showWaypoints, previewMode, tool, category, selection, onSelect, apply, preview, commit, onMessage }: {
  guide: Guide; map: MapInfo | null; background: Background; opacity: number; showWaypoints: boolean; previewMode: boolean
  tool: Tool; category: string; selection: Selection; onSelect: (s: Selection) => void
  apply: (next: Guide | ((g: Guide) => Guide)) => void; preview: (g: Guide) => void; commit: (before: Guide) => void; onMessage: (m: string) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  // 처음 보이는 범위: 지도(+2 m). 그릴 때는 대부분 지도 근처이므로. 「전체」는 그리기 영역 전체
  const mapView = () => map ? viewBoxAround({ x_min: map.origin[0], y_min: map.origin[1], x_max: map.origin[0] + map.width * map.resolution, y_max: map.origin[1] + map.height * map.resolution }, 2) : viewBoxOf(guide.bounds)
  const [box, setBox] = useState<number[]>(mapView)
  const editBox = useRef<number[] | null>(null)
  const [gesture, setGesture] = useState<Gesture | null>(null)
  const [path, setPath] = useState<Point[]>([])          // 다각형 도구로 찍는 중인 점
  const [hover, setHover] = useState<Point | null>(null)
  const bounds = guide.bounds
  const unit = Math.max(box[2], box[3]) / 100            // 손잡이·글자 크기 (보이는 범위 기준)

  const boundsKey = `${bounds.x_min},${bounds.y_min},${bounds.x_max},${bounds.y_max}`
  useEffect(() => { setBox(mapView()) }, [boundsKey, !!map])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // 미리보기: 방문자 화면처럼 그린 것에 맞춘다. 끝나면 보던 범위로
    if (previewMode) { editBox.current = box; const c = contentBox(guide); setBox(c ? viewBoxAround(c, 1.5) : viewBoxOf(bounds)) }
    else if (editBox.current) { setBox(editBox.current); editBox.current = null }
  }, [previewMode])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (tool !== 'polygon') setPath([]) }, [tool])

  /** 화면 좌표 → 미터 (격자에 맞추고 그리기 영역 안으로) */
  const toMeters = (event: { clientX: number; clientY: number; altKey?: boolean }, snapped = true): Point => {
    const svg = svgRef.current!, matrix = svg.getScreenCTM()
    if (!matrix) return [0, 0]
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    const raw: Point = [p.x, -p.y]
    return clampPoint(snapped ? snapPoint(raw, event.altKey ? FINE_SNAP_M : undefined) : raw, bounds)
  }

  const finishPolygon = (points: Point[]) => {
    if (points.length < 3) { onMessage('다각형은 점이 3개 이상이어야 합니다.'); return }
    if (!simplePolygon(points)) { onMessage('변이 엇갈리는 모양은 만들 수 없습니다. 다시 그려 주세요.'); setPath([]); return }
    apply(g => ({ ...g, areas: [...g.areas, { name: nextName('새 구역', g.areas.map(a => a.name)), category, polygon: points }] }))
    onSelect({ kind: 'area', index: guide.areas.length })
    setPath([])
    onMessage('구역을 만들었습니다. 오른쪽에서 이름과 종류를 정하세요.')
  }

  const hitOf = (target: EventTarget | null) => {
    const el = (target as Element | null)?.closest?.('[data-hit]')
    const [kind, a, b] = (el?.getAttribute('data-hit') ?? '').split(':')
    return { kind, index: Number(a), vertex: Number(b) }
  }

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || previewMode) return
    // 입력 칸에 있던 초점을 뺀다: 고치던 이름이 저장되고(onBlur), Enter·Delete가 그리기 판으로 간다
    if (document.activeElement instanceof HTMLElement && document.activeElement.closest('input, select, textarea')) document.activeElement.blur()
    const svg = svgRef.current!
    const point = toMeters(event)
    const hit = hitOf(event.target)
    if (tool === 'rect') { svg.setPointerCapture(event.pointerId); setGesture({ kind: 'rect', start: point, end: point }); return }
    if (tool === 'marker') {
      apply(g => ({ ...g, markers: [...g.markers, { name: nextName('새 표시', g.markers.map(m => m.name)), category, x: point[0], y: point[1] }] }))
      onSelect({ kind: 'marker', index: guide.markers.length })
      onMessage('표시점을 만들었습니다. 오른쪽에서 이름과 종류를 정하세요.')
      return
    }
    if (tool === 'polygon') {
      const near = path.length >= 3 && Math.hypot(point[0] - path[0][0], point[1] - path[0][1]) <= unit * 1.6
      if (near) finishPolygon(path)
      else if (!path.some(p => p[0] === point[0] && p[1] === point[1])) setPath([...path, point])
      return
    }
    // 선택 도구
    svg.setPointerCapture(event.pointerId)
    if (hit.kind === 'vertex') { setGesture({ kind: 'vertex', index: hit.index, vertex: hit.vertex, before: guide }); return }
    if (hit.kind === 'mid') {
      // 변 가운데 손잡이: 그 자리에 꼭짓점을 넣고 바로 끈다
      const polygon = [...guide.areas[hit.index].polygon]
      polygon.splice(hit.vertex + 1, 0, point)
      const next = { ...guide, areas: guide.areas.map((a, i) => i === hit.index ? { ...a, polygon } : a) }
      preview(next)
      setGesture({ kind: 'vertex', index: hit.index, vertex: hit.vertex + 1, before: guide })
      return
    }
    if (hit.kind === 'area') { onSelect({ kind: 'area', index: hit.index }); setGesture({ kind: 'move-area', index: hit.index, start: point, last: point, before: guide }); return }
    if (hit.kind === 'marker') { onSelect({ kind: 'marker', index: hit.index }); setGesture({ kind: 'move-marker', index: hit.index, before: guide }); return }
    onSelect(null)
    setGesture({ kind: 'pan', startX: event.clientX, startY: event.clientY, box })
  }

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (tool === 'polygon' || tool === 'rect' || tool === 'marker') setHover(toMeters(event))
    if (!gesture) return
    const point = toMeters(event)
    if (gesture.kind === 'pan') {
      const svg = svgRef.current!, scale = gesture.box[2] / svg.clientWidth
      const [w, h] = [gesture.box[2], gesture.box[3]]
      // 화면 비율 때문에 보이는 폭이 viewBox보다 넓을 수 있으므로 큰 쪽 비율로 옮긴다
      const s = Math.max(scale, h / svg.clientHeight)
      setBox([gesture.box[0] - (event.clientX - gesture.startX) * s, gesture.box[1] - (event.clientY - gesture.startY) * s, w, h])
    } else if (gesture.kind === 'rect') {
      setGesture({ ...gesture, end: point })
    } else if (gesture.kind === 'move-area') {
      const area = gesture.before.areas[gesture.index]
      const b = bbox(area.polygon)
      // 그리기 영역 밖으로 나가지 않게 이동량을 묶는다
      const dx = Math.min(bounds.x_max - b.x_max, Math.max(bounds.x_min - b.x_min, point[0] - gesture.start[0]))
      const dy = Math.min(bounds.y_max - b.y_max, Math.max(bounds.y_min - b.y_min, point[1] - gesture.start[1]))
      const polygon = area.polygon.map(([x, y]) => [Math.round((x + dx) * 1000) / 1000, Math.round((y + dy) * 1000) / 1000] as Point)
      preview({ ...gesture.before, areas: gesture.before.areas.map((a, i) => i === gesture.index ? { ...a, polygon } : a) })
    } else if (gesture.kind === 'move-marker') {
      preview({ ...gesture.before, markers: gesture.before.markers.map((m, i) => i === gesture.index ? { ...m, x: point[0], y: point[1] } : m) })
    } else if (gesture.kind === 'vertex') {
      const current = guide.areas[gesture.index]
      const polygon = current.polygon.map((p, i) => i === gesture.vertex ? point : p)
      preview({ ...guide, areas: guide.areas.map((a, i) => i === gesture.index ? { ...a, polygon } : a) })
    }
  }

  const onPointerUp = () => {
    if (!gesture) return
    if (gesture.kind === 'rect') {
      const [a, b] = [gesture.start, gesture.end]
      if (Math.abs(a[0] - b[0]) >= 0.25 && Math.abs(a[1] - b[1]) >= 0.25) {
        apply(g => ({ ...g, areas: [...g.areas, { name: nextName('새 구역', g.areas.map(x => x.name)), category, polygon: rectangle(a, b) }] }))
        onSelect({ kind: 'area', index: guide.areas.length })
        onMessage('구역을 만들었습니다. 오른쪽에서 이름과 종류를 정하세요.')
      }
    } else if (gesture.kind === 'vertex') {
      const polygon = guide.areas[gesture.index].polygon
      if (!simplePolygon(polygon)) { preview(gesture.before); onMessage('변이 엇갈리거나 점이 겹쳐서 되돌렸습니다.') }
      else commit(gesture.before)
    } else if (gesture.kind === 'move-area' || gesture.kind === 'move-marker') commit(gesture.before)
    setGesture(null)
  }

  const zoom = (factor: number, cx?: number, cy?: number) => {
    const [x, y, w, h] = box
    const px = cx ?? x + w / 2, py = cy ?? y + h / 2
    const full = viewBoxOf(bounds)
    const nw = Math.min(Math.max(w * factor, 2), full[2] * 2), nh = nw * h / w
    setBox([px - (px - x) * nw / w, py - (py - y) * nh / h, nw, nh])
  }
  useEffect(() => {
    // 휠 확대는 페이지 스크롤을 막아야 하므로 passive가 아닌 리스너로 단다
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const matrix = svg.getScreenCTM()
      if (!matrix) return
      const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
      zoom(event.deltaY > 0 ? 1.15 : 1 / 1.15, p.x, p.y)
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  })

  useEffect(() => {
    // 키보드: 그리기 판에 초점이 없어도 쓰되, 글자를 입력하는 칸에서는 쓰지 않는다
    const onKey = (event: KeyboardEvent) => {
      const typing = (event.target as HTMLElement | null)?.closest?.('input, textarea, select, [contenteditable]')
      if (typing || previewMode) return
      if (tool === 'polygon' && path.length) {
        if (event.key === 'Enter') { event.preventDefault(); finishPolygon(path) }
        else if (event.key === 'Escape') { event.preventDefault(); setPath([]) }
        else if (event.key === 'Backspace') { event.preventDefault(); setPath(path.slice(0, -1)) }
        return
      }
      if (event.key === 'Escape') onSelect(null)
      if (!selection) return
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault()
        apply(g => selection.kind === 'area' ? { ...g, areas: g.areas.filter((_, i) => i !== selection.index) } : { ...g, markers: g.markers.filter((_, i) => i !== selection.index) })
        onSelect(null)
        return
      }
      const step = event.altKey ? FINE_SNAP_M : 0.25
      const delta: Record<string, Point> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }
      const d = delta[event.key]
      if (!d) return
      event.preventDefault()
      apply(g => moveBy(g, selection, d))
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  })

  const selectedArea = !previewMode && selection?.kind === 'area' ? guide.areas[selection.index] : undefined
  const drawingRect = gesture?.kind === 'rect' ? rectangle(gesture.start, gesture.end) : null
  const grid: string[] = []
  if (!previewMode) {
    for (let x = Math.ceil(bounds.x_min); x <= bounds.x_max; x++) grid.push(`M${x} ${svgY(bounds.y_max)}V${svgY(bounds.y_min)}`)
    for (let y = Math.ceil(bounds.y_min); y <= bounds.y_max; y++) grid.push(`M${bounds.x_min} ${svgY(y)}H${bounds.x_max}`)
  }
  const mapHref = !map ? null : background === 'sketch' ? (map.sketch ?? map.image) : background === 'original' ? map.image : null
  return <div className={`guide-canvas tool-${tool} ${previewMode ? 'previewing' : ''}`}>
    <svg ref={svgRef} viewBox={box.join(' ')} role="application" aria-label="약도 그리기 판" data-testid="guide-canvas"
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
      onPointerLeave={() => setHover(null)} onDoubleClick={() => { if (tool === 'polygon' && path.length >= 3) finishPolygon(path) }}>
      <rect x={bounds.x_min} y={svgY(bounds.y_max)} width={bounds.x_max - bounds.x_min} height={bounds.y_max - bounds.y_min} className="guide-paper" />
      {map && !previewMode && <MapLayer map={map} href={mapHref} opacity={opacity} />}
      {!previewMode && <path d={grid.join('')} className="guide-grid" vectorEffect="non-scaling-stroke" />}
      {map && !previewMode && <rect className="guide-map-extent" x={map.origin[0]} y={svgY(map.origin[1] + map.height * map.resolution)} width={map.width * map.resolution} height={map.height * map.resolution} vectorEffect="non-scaling-stroke" />}
      <GuideDrawing guide={guide} selected={previewMode ? null : selection} />
      {showWaypoints && !previewMode && map?.waypoints.map(w => <WaypointMark key={w.name} w={w} unit={unit} />)}
      {selectedArea && <g className="guide-handles">
        {selectedArea.polygon.map(([x, y], i) => {
          const [nx, ny] = selectedArea.polygon[(i + 1) % selectedArea.polygon.length]
          return <circle key={`mid${i}`} data-hit={`mid:${selection!.index}:${i}`} className="guide-mid" cx={(x + nx) / 2} cy={svgY((y + ny) / 2)} r={unit * 0.7} vectorEffect="non-scaling-stroke"><title>끌어서 꼭짓점 추가</title></circle>
        })}
        {selectedArea.polygon.map(([x, y], i) => <circle key={`v${i}`} data-hit={`vertex:${selection!.index}:${i}`} data-testid="guide-vertex" className="guide-vertex" cx={x} cy={svgY(y)} r={unit * 0.9} vectorEffect="non-scaling-stroke"><title>끌어서 꼭짓점 옮기기</title></circle>)}
      </g>}
      {drawingRect && <polygon className="guide-drawing-shape" points={drawingRect.map(([x, y]) => `${x},${svgY(y)}`).join(' ')} vectorEffect="non-scaling-stroke" />}
      {tool === 'polygon' && path.length > 0 && <g className="guide-drawing-path">
        <polyline points={[...path, ...(hover ? [hover] : [])].map(([x, y]) => `${x},${svgY(y)}`).join(' ')} vectorEffect="non-scaling-stroke" />
        {path.map(([x, y], i) => <circle key={i} cx={x} cy={svgY(y)} r={unit * (i === 0 && path.length >= 3 ? 1.4 : 0.7)} className={i === 0 ? 'first' : ''} vectorEffect="non-scaling-stroke" />)}
      </g>}
      {hover && tool !== 'select' && !previewMode && <circle className="guide-cursor" cx={hover[0]} cy={svgY(hover[1])} r={unit * 0.5} vectorEffect="non-scaling-stroke" />}
    </svg>
    <div className="guide-zoom" role="group" aria-label="확대">
      <button type="button" onClick={() => zoom(1 / 1.4)} aria-label="확대">＋</button>
      <button type="button" onClick={() => zoom(1.4)} aria-label="축소">－</button>
      {map && <button type="button" onClick={() => setBox(mapView())}>지도</button>}
      <button type="button" onClick={() => setBox(viewBoxOf(bounds))}>전체</button>
    </div>
    {hover && tool !== 'select' && <span className="guide-coords" role="status">{hover[0].toFixed(2)}, {hover[1].toFixed(2)} m</span>}
  </div>
}

function MapLayer({ map, href, opacity }: { map: MapInfo; href: string | null; opacity: number }) {
  const [w, h] = [map.width * map.resolution, map.height * map.resolution]
  const y = svgY(map.origin[1] + h)
  return href
    ? <image href={href} x={map.origin[0]} y={y} width={w} height={h} opacity={opacity} preserveAspectRatio="none" className={href.includes('sketch') ? 'map-sketch' : 'map-image'} data-testid="guide-map" />
    : <rect x={map.origin[0]} y={y} width={w} height={h} className="map-blank" opacity={opacity} />
}

function WaypointMark({ w, unit }: { w: Waypoint; unit: number }) {
  return <g className="guide-waypoint" pointerEvents="none">
    <circle cx={w.x} cy={svgY(w.y)} r={unit * 0.7} vectorEffect="non-scaling-stroke" />
    <text x={w.x + unit} y={svgY(w.y) - unit} fontSize={unit * 1.5}>{w.name}</text>
  </g>
}

/** 고른 구역·표시점을 d만큼 옮긴다. 그리기 영역 밖으로는 가지 않는다 */
export function moveBy(g: Guide, selection: NonNullable<Selection>, [dx, dy]: Point): Guide {
  const b: Bounds = g.bounds
  if (selection.kind === 'marker') {
    const m = g.markers[selection.index]
    if (!m) return g
    const [x, y] = clampPoint([m.x + dx, m.y + dy], b)
    return { ...g, markers: g.markers.map((v, i) => i === selection.index ? { ...v, x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 } : v) }
  }
  const a = g.areas[selection.index]
  if (!a) return g
  const moved = a.polygon.map(([x, y]) => [Math.round((x + dx) * 1000) / 1000, Math.round((y + dy) * 1000) / 1000] as Point)
  if (!moved.every(p => inside(p, b))) return g
  return { ...g, areas: g.areas.map((v, i) => i === selection.index ? { ...v, polygon: moved } : v) }
}
