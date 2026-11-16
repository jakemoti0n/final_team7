// 방문자 안내 화면의 데이터. 서버 GET /api/v1/visitor/state (로그인 없음, 읽기 전용)와 같은 모양
import type { Tone } from '../../status'
import type { MapInfo } from '../../map'

export type VisitorStatus = 'patrolling' | 'paused' | 'idle' | 'checking' | 'offline'
export interface VisitorPosition { x: number; y: number; stale: boolean; age_s: number | null }
export interface VisitorRobot { robot_id: string; status: VisitorStatus; position: VisitorPosition | null }
export interface VisitorMap { resolution: number; origin: number[]; width: number; height: number; image: string | null }
export interface VisitorState { server_utc: string; robots: VisitorRobot[]; operating: number; map: VisitorMap | null }

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

/** 서버 응답 검사. 모양이 다르면 null (받지 못한 것으로 본다) */
export function parseVisitorState(value: unknown): VisitorState | null {
  const v = value as VisitorState
  if (!v || typeof v.server_utc !== 'string' || !finite(v.operating) || !Array.isArray(v.robots)) return null
  for (const r of v.robots) {
    if (!r || typeof r.robot_id !== 'string' || !statuses.includes(r.status)) return null
    const p = r.position
    if (p !== null && (!p || !finite(p.x) || !finite(p.y) || typeof p.stale !== 'boolean' || (p.age_s !== null && !finite(p.age_s)))) return null
  }
  const m = v.map
  if (m !== null && (!m || !(m.resolution > 0) || !Array.isArray(m.origin) || m.origin.length < 2 || !(m.width > 0) || !(m.height > 0))) return null
  return v
}

/** 지도 그리기용 (MapInfo의 좌표 변환을 그대로 쓴다. 방문자 화면에는 순찰 지점이 없다) */
export function mapInfo(map: VisitorMap): MapInfo {
  return { ...map, waypoints: [] }
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

/** t초 시점의 데모 상태. LIMBO-01은 사각형 경로를 돌고, LIMBO-02는 대기, LIMBO-03은 끊긴 지 48초 */
export function demoVisitorState(t: number, now = new Date()): VisitorState {
  const corners: [number, number][] = [[5, 5], [-5, 5], [-5, -5], [5, -5]]
  const leg = Math.floor(t / 10) % 4, f = (t % 10) / 10
  const [ax, ay] = corners[leg], [bx, by] = corners[(leg + 1) % 4]
  const half = (n: number) => Math.round(n * 2) / 2
  return {
    server_utc: now.toISOString(), operating: 2, map: DEMO_MAP,
    robots: [
      { robot_id: 'LIMBO-01', status: 'patrolling', position: { x: half(ax + (bx - ax) * f), y: half(ay + (by - ay) * f), stale: false, age_s: 0 } },
      { robot_id: 'LIMBO-02', status: 'idle', position: { x: 3, y: -4, stale: false, age_s: 0 } },
      { robot_id: 'LIMBO-03', status: 'offline', position: { x: -4.5, y: 1, stale: true, age_s: 48 } },
    ],
  }
}
