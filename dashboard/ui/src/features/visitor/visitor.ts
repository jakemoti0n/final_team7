// 방문자 안내 화면의 데이터. 서버 GET /api/v1/visitor/state (로그인 없음, 읽기 전용)와 같은 모양
import type { Tone } from '../../status'
import type { MapInfo } from '../../map'
import { demoGuide } from '../guide/demoGuide'
import { iconNames, type Area, type Bounds, type Category, type Guide, type Marker, type Transform } from '../guide/guide'

export type VisitorStatus = 'patrolling' | 'paused' | 'idle' | 'checking' | 'offline'
export interface VisitorPosition { x: number; y: number; stale: boolean; age_s: number | null }
/** area: 로봇이 있는 약도 구역 이름, next_area: 다음 목표가 있는 구역 이름, progress: 순찰 진행(done = 다음 목표 번호),
 *  moving: 순찰 중이면서 앞으로 가는 중 (모르면 null). 예전 서버면 없을 수 있다 */
export interface VisitorProgress { done: number; total: number }
export interface VisitorRobot {
  robot_id: string; status: VisitorStatus; position: VisitorPosition | null
  area?: string | null; next_area?: string | null; progress?: VisitorProgress | null; moving?: boolean | null
}
export interface VisitorMap { resolution: number; origin: number[]; width: number; height: number; image: string | null; sketch?: string | null }
/** guide: 안내 약도의 판(revision). 바뀌면 GET /api/v1/visitor/guide로 다시 받는다. 없으면 null (자동 약도가 메인) */
/** display: 하단 디스플레이 내용(일정·팜플렛)의 판. 바뀌면 GET /api/v1/display/content로 다시 받는다 */
export interface VisitorState { server_utc: string; robots: VisitorRobot[]; operating: number; map: VisitorMap | null; guide?: string | null; display?: string | null }
/** 방문자용 안내 약도 (관제 화면 '약도 편집'에서 그림). 기준점·지도 이름·순찰 지점은 없다 */
export interface VisitorGuide {
  revision: string; bounds: Bounds; categories: Category[]; areas: Area[]; markers: Marker[]
  image: { file: string; width: number; height: number; transform: Transform; show_areas: boolean; url: string } | null
}

/** 방문자에게 보이는 상태 문구. 색만으로 구분하지 않도록 배지 기호(Badge)와 함께 쓴다 */
export const visitorStatus: Record<VisitorStatus, { label: string; tone: Tone }> = {
  patrolling: { label: '순찰 중', tone: 'good' },
  paused: { label: '잠시 멈춤', tone: 'warn' },
  idle: { label: '대기 중', tone: 'neutral' },
  checking: { label: '상태 확인 중', tone: 'neutral' },
  offline: { label: '연결 끊김', tone: 'bad' },
}

const statuses = Object.keys(visitorStatus)
const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value)
const optionalText = (value: unknown) => value == null || typeof value === 'string'

/** 서버 응답 검사. 모양이 다르면 null (받지 못한 것으로 본다) */
export function parseVisitorState(value: unknown): VisitorState | null {
  const v = value as VisitorState
  if (!v || typeof v.server_utc !== 'string' || !finite(v.operating) || !Array.isArray(v.robots)) return null
  for (const r of v.robots) {
    if (!r || typeof r.robot_id !== 'string' || !statuses.includes(r.status)) return null
    const p = r.position
    if (p !== null && (!p || !finite(p.x) || !finite(p.y) || typeof p.stale !== 'boolean' || (p.age_s !== null && !finite(p.age_s)))) return null
    if (!optionalText(r.area) || !optionalText(r.next_area)) return null
    const g = r.progress
    if (g != null && (!Number.isInteger(g.done) || !Number.isInteger(g.total) || g.done < 0 || g.total <= 0 || g.done > g.total)) return null
    if (r.moving != null && typeof r.moving !== 'boolean') return null
  }
  const m = v.map
  if (m !== null && (!m || !(m.resolution > 0) || !Array.isArray(m.origin) || m.origin.length < 2 || !(m.width > 0) || !(m.height > 0))) return null
  return v
}

const color = (v: unknown) => typeof v === 'string' && /^#[0-9A-Fa-f]{6}$/.test(v)
const point = (p: unknown) => Array.isArray(p) && p.length === 2 && finite(p[0]) && finite(p[1])

/** 방문자 약도 응답 검사. 모양이 다르면 null (그리지 않고 자동 약도로) */
export function parseVisitorGuide(value: unknown): VisitorGuide | null {
  const g = value as VisitorGuide
  if (!g || typeof g.revision !== 'string' || !g.bounds || !['x_min', 'y_min', 'x_max', 'y_max'].every(k => finite(g.bounds[k as keyof Bounds]))) return null
  if (!Array.isArray(g.categories) || !g.categories.every(c => c && typeof c.key === 'string' && typeof c.label === 'string' && color(c.color) && (iconNames as readonly string[]).includes(c.icon))) return null
  if (!Array.isArray(g.areas) || !g.areas.every(a => a && typeof a.name === 'string' && typeof a.category === 'string' && Array.isArray(a.polygon) && a.polygon.length >= 3 && a.polygon.every(point))) return null
  if (!Array.isArray(g.markers) || !g.markers.every(m => m && typeof m.name === 'string' && typeof m.category === 'string' && finite(m.x) && finite(m.y))) return null
  const i = g.image
  if (i !== null && (!i || typeof i.url !== 'string' || !i.url.startsWith('/api/v1/visitor/guide/image/') || !finite(i.width) || !finite(i.height)
    || !Array.isArray(i.transform) || i.transform.length !== 6 || !i.transform.every(finite) || typeof i.show_areas !== 'boolean')) return null
  return g
}

/** 약도 그리기(GuideDrawing)용으로 */
export function asGuide(g: VisitorGuide): Guide {
  return { version: 1, map: null, bounds: g.bounds, categories: g.categories, areas: g.areas, markers: g.markers,
    image: g.image ? { file: g.image.file, width: g.image.width, height: g.image.height, transform: g.image.transform, points: [], show_areas: g.image.show_areas } : null }
}

/** 지도 그리기용 (MapInfo의 좌표 변환을 그대로 쓴다. 방문자 화면에는 순찰 지점이 없다) */
export function mapInfo(map: VisitorMap): MapInfo {
  return { ...map, waypoints: [] }
}

/**
 * 점선 원(마지막으로 확인한 위치)의 stroke-dasharray. 둘레를 n칸으로 똑같이 나눠 이음매에서 점이 붙거나 잘리지 않게 한다.
 * pathLength는 옛 Safari가 원에서 무시하므로 쓰지 않고 실제 길이로 계산한다.
 */
export function dashedCircle(r: number, n = 10) {
  const step = 2 * Math.PI * r / n
  return `${+(step * .55).toFixed(4)} ${+(step * .45).toFixed(4)}`
}

/** 위치를 받은 뒤 지난 시간(초): 서버가 알려 준 나이 + 받은 뒤 화면에서 지난 시간 */
export function positionAge(position: VisitorPosition, sinceReceived: number) {
  return position.age_s === null ? null : position.age_s + Math.max(0, sinceReceived)
}

/** "순찰 로봇 N대 운행 중" 문구. 서버에서 받지 못하고 있으면 지금 대수를 모른다고 말한다 */
export function operatingText(state: VisitorState | null, problem: boolean) {
  if (!state) return problem ? '로봇 정보를 받을 수 없습니다' : '로봇 정보를 불러오는 중입니다'
  if (problem) return '지금 운행 대수를 확인할 수 없습니다'
  return state.operating > 0 ? `LIMBO ${state.operating}대 운행 중` : '지금 운행 중인 LIMBO가 없습니다'
}

// ---- 데모 (/visitor?demo): 서버 없이 가상 로봇 3대 ----
const DEMO_MAP: VisitorMap = { resolution: .05, origin: [-7.546, -7.524, 0], width: 302, height: 302, image: null }

/** (x, y)가 들어 있는 구역 이름. 겹치면 가장 작은 구역 (서버 guide.py의 area_at과 같은 규칙) */
export function areaAt(areas: Area[], x: number, y: number): string | null {
  let best: { size: number; name: string } | null = null
  for (const a of areas) {
    const p = a.polygon
    let inside = false, twice = 0
    for (let i = 0; i < p.length; i++) {
      const [x0, y0] = p[i], [x1, y1] = p[(i + 1) % p.length]
      if ((y0 > y) !== (y1 > y) && x < x0 + (y - y0) * (x1 - x0) / (y1 - y0)) inside = !inside
      twice += x0 * y1 - x1 * y0
    }
    const size = Math.abs(twice) / 2
    if (inside && (!best || size < best.size || (size === best.size && a.name < best.name))) best = { size, name: a.name }
  }
  return best?.name ?? null
}

/** t초 시점의 데모 상태. LIMBO-01은 사각형 경로(모서리 4곳이 순찰 지점)를 돌고, LIMBO-02는 대기, LIMBO-03은 끊긴 지 48초.
 *  구역 이름은 데모 약도(demoGuide)로 계산한다. 모서리마다 3초 멈췄다 출발한다(하단 디스플레이의 「지나갑니다」 데모) */
export function demoVisitorState(t: number, now = new Date()): VisitorState {
  const corners: [number, number][] = [[5, 5], [-5, 5], [-5, -5], [5, -5]]
  const leg = Math.floor(t / 13) % 4, local = t % 13, f = Math.max(0, local - 3) / 10
  const [ax, ay] = corners[leg], [bx, by] = corners[(leg + 1) % 4]
  const half = (n: number) => Math.round(n * 2) / 2
  const x = ax + (bx - ax) * f, y = ay + (by - ay) * f
  const areas = demoGuide().areas
  return {
    server_utc: now.toISOString(), operating: 2, map: DEMO_MAP, guide: 'demo', display: 'demo',
    robots: [
      { robot_id: 'LIMBO-01', status: 'patrolling', position: { x: half(x), y: half(y), stale: false, age_s: 0 },
        area: areaAt(areas, x, y), next_area: areaAt(areas, bx, by), progress: { done: (leg + 1) % 4, total: 4 }, moving: local >= 3 },
      { robot_id: 'LIMBO-02', status: 'idle', position: { x: 3, y: -4, stale: false, age_s: 0 },
        area: areaAt(areas, 3, -4), next_area: null, progress: null, moving: false },
      { robot_id: 'LIMBO-03', status: 'offline', position: { x: -4.5, y: 1, stale: true, age_s: 48 },
        area: areaAt(areas, -4.5, 1), next_area: null, progress: null, moving: false },
    ],
  }
}

/** 데모 안내 약도: 관제 화면 데모(/demo?page=guide)와 같은 예시 구역 */
export function demoVisitorGuide(): VisitorGuide {
  const g = demoGuide()
  return { revision: 'demo', bounds: g.bounds, categories: g.categories, areas: g.areas, markers: g.markers, image: null }
}
