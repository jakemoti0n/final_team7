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
/** 그림 픽셀 (u, v) → 지도 (x, y): x = a·u + b·v + c, y = d·u + e·v + f */
export type Transform = [number, number, number, number, number, number]
export interface PointPair { image: Point; map: Point }
/** 메인 약도를 그림 파일로 쓸 때. 그림은 서버에 따로 올리고(PUT /api/v1/guide/image) 이름만 둔다 */
export interface GuideImage { file: string; width: number; height: number; transform: Transform; points: PointPair[]; show_areas: boolean }
export interface Guide { version: 1; map: string | null; bounds: Bounds; categories: Category[]; areas: Area[]; markers: Marker[]; image: GuideImage | null }
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
  return { version: 1, map: mapName, bounds: mapBounds(map, BOUNDS_MARGIN_M), categories: defaultCategories.map(c => ({ ...c })), areas: [], markers: [], image: null }
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

// ---- 그림 약도: 그림 픽셀 ↔ 지도 m ----

export const TEMPLATE_PX_PER_M = [20, 40]

export function applyTransform([a, b, c, d, e, f]: Transform, [u, v]: Point): Point { return [a * u + b * v + c, d * u + e * v + f] }

export function imageCorners(image: Pick<GuideImage, 'transform' | 'width' | 'height'>): Point[] {
  return ([[0, 0], [image.width, 0], [image.width, image.height], [0, image.height]] as Point[]).map(p => applyTransform(image.transform, p))
}

/** SVG(미터, y 뒤집음)에 그림을 놓는 matrix(): 그림 (u, v) → (x, −y) */
export function svgMatrix([a, b, c, d, e, f]: Transform) { return `matrix(${a} ${-d} ${b} ${-e} ${c} ${-f})` }

/** 틀 그림: 그리기 영역 왼쪽 위가 (0, 0), 1 m = ppm px */
export function templateSize(b: Bounds, ppm: number) { return [Math.round((b.x_max - b.x_min) * ppm), Math.round((b.y_max - b.y_min) * ppm)] }
export function templateTransform(b: Bounds, ppm: number): Transform { return [1 / ppm, 0, b.x_min, 0, -1 / ppm, b.y_max] }
/** 올린 그림이 지금 영역의 틀 크기와 같으면 그 1 m당 px (±1 px). 아니면 null */
export function matchTemplate(b: Bounds, width: number, height: number) {
  return TEMPLATE_PX_PER_M.find(ppm => { const [w, h] = templateSize(b, ppm); return Math.abs(w - width) <= 1 && Math.abs(h - height) <= 1 }) ?? null
}

function solve3(m: number[][], r: number[]): number[] | null {
  // 가우스 소거 (부분 피벗)
  const a = m.map((row, i) => [...row, r[i]])
  for (let col = 0; col < 3; col++) {
    let pivot = col
    for (let row = col + 1; row < 3; row++) if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row
    if (Math.abs(a[pivot][col]) < 1e-12) return null
    ;[a[col], a[pivot]] = [a[pivot], a[col]]
    for (let row = 0; row < 3; row++) if (row !== col) {
      const f = a[row][col] / a[col][col]
      for (let k = col; k < 4; k++) a[row][k] -= f * a[col][k]
    }
  }
  return [a[0][3] / a[0][0], a[1][3] / a[1][1], a[2][3] / a[2][2]]
}

/**
 * 기준점 짝(3개 이상)으로 그림 → 지도 변환을 최소제곱으로 구한다(늘리기·회전·기울이기·이동).
 * 점들이 거의 한 줄이면 null. 결과에 점마다의 어긋남(m)을 같이 준다
 */
export function fitTransform(pairs: PointPair[]): { transform: Transform; errors: number[]; rms: number } | null {
  if (pairs.length < 3) return null
  // 숫자 크기를 맞추려고 그림 좌표를 가운데·크기로 정규화한 뒤 푼다
  const n = pairs.length
  const mu = pairs.reduce((s, p) => s + p.image[0], 0) / n, mv = pairs.reduce((s, p) => s + p.image[1], 0) / n
  const scale = Math.max(1e-9, Math.sqrt(pairs.reduce((s, p) => s + (p.image[0] - mu) ** 2 + (p.image[1] - mv) ** 2, 0) / n))
  const rows = pairs.map(p => [(p.image[0] - mu) / scale, (p.image[1] - mv) / scale, 1])
  const m = [0, 1, 2].map(i => [0, 1, 2].map(j => rows.reduce((s, r) => s + r[i] * r[j], 0)))
  const det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  if (Math.abs(det) < 1e-6 * n ** 3) return null
  const rx = [0, 1, 2].map(i => rows.reduce((s, r, k) => s + r[i] * pairs[k].map[0], 0))
  const ry = [0, 1, 2].map(i => rows.reduce((s, r, k) => s + r[i] * pairs[k].map[1], 0))
  const px = solve3(m, rx), py = solve3(m, ry)
  if (!px || !py) return null
  // 정규화를 풀어 원래 그림 좌표의 계수로
  const a = px[0] / scale, b = px[1] / scale, c = px[2] - a * mu - b * mv
  const d = py[0] / scale, e = py[1] / scale, f = py[2] - d * mu - e * mv
  const transform: Transform = [a, b, c, d, e, f]
  if (Math.abs(a * e - b * d) < 1e-12) return null
  const errors = pairs.map(p => { const [x, y] = applyTransform(transform, p.image); return Math.hypot(x - p.map[0], y - p.map[1]) })
  return { transform, errors, rms: Math.sqrt(errors.reduce((s, v) => s + v * v, 0) / n) }
}

/** 영역이 상자를 담도록 넓힌다 (사방 1 m 여유, 이미 담으면 그대로) */
export function boundsCovering(b: Bounds, points: Point[], margin = 1): Bounds {
  const box = bbox(points)
  const r = (v: number) => Math.round(v * 1000) / 1000
  return {
    x_min: box.x_min < b.x_min ? r(Math.floor(box.x_min - margin)) : b.x_min, y_min: box.y_min < b.y_min ? r(Math.floor(box.y_min - margin)) : b.y_min,
    x_max: box.x_max > b.x_max ? r(Math.ceil(box.x_max + margin)) : b.x_max, y_max: box.y_max > b.y_max ? r(Math.ceil(box.y_max + margin)) : b.y_max,
  }
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
  if (g.image && !imageCorners(g.image).every(([x, y]) => inside([round3(x), round3(y)], b))) out.push('약도 그림이 그리기 영역 밖으로 나갑니다. 영역을 넓히세요.')
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

/** 그린 것(구역·표시점·그림) 전체를 담는 상자. 없으면 null */
export function contentBox(g: Guide): Bounds | null {
  const points: Point[] = [...g.areas.flatMap(a => a.polygon), ...g.markers.map(m => [m.x, m.y] as Point), ...(g.image ? imageCorners(g.image) : [])]
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
  if (d?.guide && d.guide.image === undefined) d.guide.image = null   // 예전 서버
  return !!d && typeof d.revision === 'string' && !!d.guide && Array.isArray(d.guide.areas) && Array.isArray(d.guide.categories) && Array.isArray(d.guide.markers) && !!d.guide.bounds
}
