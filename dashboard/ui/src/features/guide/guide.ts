/**
 * 방문자 안내 약도: 서버 guide_yaml과 같은 형식 (dashboard/server/guide.py). 좌표는 지도와 같은 m.
 * 관제 화면 '약도 편집'이 그리고, 방문자 화면이 보여 준다.
 */
import type { MapInfo } from '../../map'

export type Point = [number, number]
export interface Bounds { x_min: number; y_min: number; x_max: number; y_max: number }
export interface Category { key: string; label: string; color: string; icon: IconName }
export interface Area { name: string; category: string; polygon: Point[] }
export interface Marker { name: string; category: string; x: number; y: number }
export interface Guide { version: 1; map: string | null; bounds: Bounds; categories: Category[]; areas: Area[]; markers: Marker[] }
export interface GuideDocument { revision: string; exists: boolean; file: string; guide: Guide; map: string; map_matches: boolean; map_bounds: Bounds }

// 서버 guide.py의 ICONS와 같게
export const iconNames = ['none', 'classroom', 'event', 'restroom', 'entrance', 'exit', 'stairs', 'elevator', 'info', 'food', 'office', 'medical', 'restricted', 'star'] as const
export type IconName = typeof iconNames[number]
export const iconLabels: Record<IconName, string> = {
  none: '없음', classroom: '강의실', event: '행사', restroom: '화장실', entrance: '입구', exit: '출구', stairs: '계단', elevator: '엘리베이터',
  info: '안내', food: '식당·카페', office: '사무실', medical: '의무실', restricted: '출입 금지', star: '추천',
}

// 서버 guide.py와 같은 한도
export const limits = { name: 32, categories: 50, areas: 300, markers: 200, points: 64, span: 1000 }
export const SNAP_M = 0.25
export const FINE_SNAP_M = 0.05      // Alt를 누른 채 그리면 이 단위
export const BOUNDS_MARGIN_M = 10

export const defaultCategories: Category[] = [
  { key: 'classroom', label: '강의실', color: '#DCE8F5', icon: 'classroom' },
  { key: 'event', label: '행사장', color: '#FCE9C8', icon: 'event' },
  { key: 'restroom', label: '화장실', color: '#DFF0E3', icon: 'restroom' },
  { key: 'entrance', label: '입구', color: '#FBE3E0', icon: 'entrance' },
  { key: 'corridor', label: '복도', color: '#F3F4F1', icon: 'none' },
  { key: 'stairs', label: '계단·엘리베이터', color: '#E8E3F4', icon: 'stairs' },
  { key: 'restricted', label: '출입 금지', color: '#E3E5E8', icon: 'restricted' },
  { key: 'other', label: '기타', color: '#FFFFFF', icon: 'none' },
]

export function mapBounds(map: MapInfo, margin = 0): Bounds {
  const r = (v: number) => Math.round(v * 1000) / 1000
  return { x_min: r(map.origin[0] - margin), y_min: r(map.origin[1] - margin), x_max: r(map.origin[0] + map.width * map.resolution + margin), y_max: r(map.origin[1] + map.height * map.resolution + margin) }
}

export function emptyGuide(map: MapInfo, mapName: string | null): Guide {
  return { version: 1, map: mapName, bounds: mapBounds(map, BOUNDS_MARGIN_M), categories: defaultCategories.map(c => ({ ...c })), areas: [], markers: [] }
}

// ---- 좌표 ----

export const round3 = (v: number) => Math.round(v * 1000) / 1000 || 0   // -0은 0으로
export function snap(v: number, step = SNAP_M) { return round3(Math.round(v / step) * step) }
export function snapPoint([x, y]: Point, step = SNAP_M): Point { return [snap(x, step), snap(y, step)] }
export function clampPoint([x, y]: Point, b: Bounds): Point { return [Math.min(b.x_max, Math.max(b.x_min, x)), Math.min(b.y_max, Math.max(b.y_min, y))] }
export function inside([x, y]: Point, b: Bounds) { return b.x_min <= x && x <= b.x_max && b.y_min <= y && y <= b.y_max }

/** 두 꼭짓점으로 축에 나란한 직사각형 (반시계) */
export function rectangle([x1, y1]: Point, [x2, y2]: Point): Point[] {
  const [a, b, c, d] = [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]
  return [[a, b], [c, b], [c, d], [a, d]]
}

/** 부호 있는 넓이 (반시계면 양수) */
export function signedArea(points: Point[]) {
  let sum = 0
  for (let i = 0; i < points.length; i++) { const [x1, y1] = points[i], [x2, y2] = points[(i + 1) % points.length]; sum += x1 * y2 - x2 * y1 }
  return sum / 2
}

export function bbox(points: Point[]) {
  const xs = points.map(p => p[0]), ys = points.map(p => p[1])
  return { x_min: Math.min(...xs), y_min: Math.min(...ys), x_max: Math.max(...xs), y_max: Math.max(...ys) }
}

export function pointInPolygon([x, y]: Point, points: Point[]) {
  let hit = false
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i], [xj, yj] = points[j]
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit
  }
  return hit
}

function orient(a: Point, b: Point, c: Point) {
  const v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
  return Math.abs(v) < 1e-9 ? 0 : v > 0 ? 1 : -1
}
function onSegment(a: Point, b: Point, c: Point) {
  return Math.min(a[0], b[0]) - 1e-9 <= c[0] && c[0] <= Math.max(a[0], b[0]) + 1e-9 && Math.min(a[1], b[1]) - 1e-9 <= c[1] && c[1] <= Math.max(a[1], b[1]) + 1e-9
}
function segmentsCross(p1: Point, p2: Point, q1: Point, q2: Point) {
  const o1 = orient(p1, p2, q1), o2 = orient(p1, p2, q2), o3 = orient(q1, q2, p1), o4 = orient(q1, q2, p2)
  if (o1 !== o2 && o3 !== o4 && o1 && o2 && o3 && o4) return true
  return (!o1 && onSegment(p1, p2, q1)) || (!o2 && onSegment(p1, p2, q2)) || (!o3 && onSegment(q1, q2, p1)) || (!o4 && onSegment(q1, q2, p2))
}

/** 서버와 같은 규칙: 꼭짓점이 겹치지 않고, 이웃하지 않은 변끼리 만나지 않으며, 넓이가 있다 */
export function simplePolygon(points: Point[]) {
  const n = points.length
  if (n < 3 || new Set(points.map(p => p.join(','))).size !== n || Math.abs(signedArea(points)) < 1e-6) return false
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    if (j === i + 1 || (i === 0 && j === n - 1)) continue
    if (segmentsCross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n])) return false
  }
  return true
}

/** 이름표 자리: 무게중심이 구역 안이면 그곳, 아니면(ㄷ자 등) 가로로 훑어 가장 넓은 칸의 가운데 */
export function labelPoint(points: Point[]): Point {
  const a = signedArea(points)
  if (Math.abs(a) > 1e-9) {
    let cx = 0, cy = 0
    for (let i = 0; i < points.length; i++) {
      const [x1, y1] = points[i], [x2, y2] = points[(i + 1) % points.length], f = x1 * y2 - x2 * y1
      cx += (x1 + x2) * f; cy += (y1 + y2) * f
    }
    const c: Point = [cx / (6 * a), cy / (6 * a)]
    if (pointInPolygon(c, points)) return c
  }
  const box = bbox(points)
  let best: Point = [(box.x_min + box.x_max) / 2, (box.y_min + box.y_max) / 2], width = -1
  for (let k = 1; k < 20; k++) {
    const y = box.y_min + (box.y_max - box.y_min) * k / 20, xs: number[] = []
    for (let i = 0; i < points.length; i++) {
      const [x1, y1] = points[i], [x2, y2] = points[(i + 1) % points.length]
      if ((y1 > y) !== (y2 > y)) xs.push(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    }
    xs.sort((p, q) => p - q)
    for (let i = 0; i + 1 < xs.length; i += 2) if (xs[i + 1] - xs[i] > width) { width = xs[i + 1] - xs[i]; best = [(xs[i] + xs[i + 1]) / 2, y] }
  }
  return best
}

/** 이름표 글자 크기(m)와 보일 것. 이름이 길면 글자를 줄여 맞추고, 그래도 안 들어가면 숨긴다.
 *  높이가 모자라면 아이콘을 먼저 뺀다 */
export function labelFit(points: Point[], name: string) {
  const box = bbox(points), w = box.x_max - box.x_min, h = box.y_max - box.y_min
  const units = [...name].reduce((sum, ch) => sum + (ch.charCodeAt(0) > 0x2e80 ? 1 : 0.6), 0) || 1   // 한글 1, 영문·숫자 0.6 글자폭
  const size = Math.min(1.1, Math.max(0.35, Math.min(w, h) * 0.22), w * 0.9 / units)
  const showText = size >= 0.25 && size * 1.3 <= h
  return { size, showText, showIcon: showText ? size * 2.7 <= h : Math.min(w, h) >= 0.8 }
}

// ---- 검사 (서버와 같은 규칙, 저장 전에 알려 주려고) ----

export function nameProblem(name: string) {
  const v = name.trim()
  if (!v || [...v].length > limits.name) return `이름은 1~${limits.name}자여야 합니다.`
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(v)) return '이름에 줄바꿈 같은 제어 문자를 넣을 수 없습니다.'
  return null
}

export function guideProblems(g: Guide): string[] {
  const out: string[] = []
  const keys = new Set(g.categories.map(c => c.key))
  if (!g.categories.length) out.push('구역 종류가 하나는 있어야 합니다.')
  if (g.categories.length > limits.categories) out.push(`구역 종류는 ${limits.categories}개까지입니다.`)
  if (g.areas.length > limits.areas) out.push(`구역은 ${limits.areas}개까지입니다.`)
  if (g.markers.length > limits.markers) out.push(`표시점은 ${limits.markers}개까지입니다.`)
  const b = g.bounds
  if (!(b.x_max > b.x_min && b.y_max > b.y_min) || b.x_max - b.x_min > limits.span || b.y_max - b.y_min > limits.span) out.push(`그리기 영역의 크기는 0보다 크고 ${limits.span} m 이하여야 합니다.`)
  for (const c of g.categories) { const p = nameProblem(c.label); if (p) out.push(`종류 「${c.label || c.key}」: ${p}`) }
  g.areas.forEach(a => {
    const p = nameProblem(a.name)
    if (p) out.push(`구역 「${a.name || '(이름 없음)'}」: ${p}`)
    if (!keys.has(a.category)) out.push(`구역 「${a.name}」: 없는 종류입니다.`)
    if (a.polygon.length > limits.points) out.push(`구역 「${a.name}」: 꼭짓점은 ${limits.points}개까지입니다.`)
    if (!simplePolygon(a.polygon)) out.push(`구역 「${a.name}」: 변이 엇갈리거나 넓이가 없습니다.`)
    if (!a.polygon.every(p => inside(p, b))) out.push(`구역 「${a.name}」: 그리기 영역 밖에 있습니다.`)
  })
  g.markers.forEach(m => {
    const p = nameProblem(m.name)
    if (p) out.push(`표시점 「${m.name || '(이름 없음)'}」: ${p}`)
    if (!keys.has(m.category)) out.push(`표시점 「${m.name}」: 없는 종류입니다.`)
    if (!inside([m.x, m.y], b)) out.push(`표시점 「${m.name}」: 그리기 영역 밖에 있습니다.`)
  })
  return out
}

/** 새 이름: 「새 구역 3」처럼 겹치지 않게 */
export function nextName(prefix: string, taken: string[]) {
  const used = new Set(taken)
  for (let i = taken.length + 1; ; i++) if (!used.has(`${prefix} ${i}`)) return `${prefix} ${i}`
}

/** 새 종류의 key: 사람이 고르지 않게 자동으로 */
export function nextCategoryKey(categories: Category[]) {
  const used = new Set(categories.map(c => c.key))
  for (let i = 1; ; i++) if (!used.has(`custom-${i}`)) return `custom-${i}`
}

/** 저장할 때 쓰는 정리: 이름 앞뒤 공백, 좌표 mm */
export function normalized(g: Guide): Guide {
  return {
    ...g,
    categories: g.categories.map(c => ({ ...c, label: c.label.trim(), color: c.color.toUpperCase() })),
    areas: g.areas.map(a => ({ ...a, name: a.name.trim(), polygon: a.polygon.map(([x, y]) => [round3(x), round3(y)] as Point) })),
    markers: g.markers.map(m => ({ ...m, name: m.name.trim(), x: round3(m.x), y: round3(m.y) })),
  }
}

/** 그린 것(구역·표시점) 전체를 담는 상자. 없으면 null */
export function contentBox(g: Guide): Bounds | null {
  const points: Point[] = [...g.areas.flatMap(a => a.polygon), ...g.markers.map(m => [m.x, m.y] as Point)]
  return points.length ? bbox(points) : null
}

/** 상자에 사방 margin(m)을 더한 viewBox (내용이 한 점뿐이어도 최소 크기는 둔다) */
export function viewBoxAround(b: Bounds, margin: number, min = 6) {
  const w = Math.max(b.x_max - b.x_min + margin * 2, min), h = Math.max(b.y_max - b.y_min + margin * 2, min)
  const cx = (b.x_min + b.x_max) / 2, cy = (b.y_min + b.y_max) / 2
  return [cx - w / 2, -(cy + h / 2), w, h]
}

/** 표시점 반지름(m): 약도 전체 크기에 맞춰 (넓은 약도에서 너무 작아지지 않게) */
export function markerRadius(g: Guide) {
  const box = contentBox(g)
  const span = box ? Math.max(box.x_max - box.x_min, box.y_max - box.y_min) : 10
  return Math.min(1.2, Math.max(0.35, span * 0.014))
}

/** 약도 좌표(m) ↔ SVG 좌표: x 그대로, y는 뒤집는다 (SVG는 y가 아래로) */
export const svgY = (y: number) => -y
export function viewBoxOf(b: Bounds) { return [b.x_min, -b.y_max, b.x_max - b.x_min, b.y_max - b.y_min] }

export function isGuideDocument(value: unknown): value is GuideDocument {
  const d = value as GuideDocument
  return !!d && typeof d.revision === 'string' && !!d.guide && Array.isArray(d.guide.areas) && Array.isArray(d.guide.categories) && Array.isArray(d.guide.markers) && !!d.guide.bounds
}
