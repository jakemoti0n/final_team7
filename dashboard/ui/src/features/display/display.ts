// 로봇 하단 디스플레이(/display)의 데이터와 규칙. 화면 없이 시험할 수 있게 순수 함수로 둔다.
// 근거: signage/docs/PRD_로봇_하단_디스플레이_v0.3.md (장면 ①-Q1·②-A·④-A·⑤ 나무, 회전 규칙 R)
import { visitorStatus, type EcoTree, type EcoView, type VisitorRobot, type VisitorState } from '../visitor/visitor'

// ---- 서버 GET /api/v1/display/content (dashboard/server/display.py) ----
export interface DisplayEvent { date: string | null; start: string; end: string | null; title: string; place: string | null }
export interface DisplaySlide { file: string; width: number; height: number; type: string; url: string }
export interface DisplayTiming {
  location_s: number; slides_s: number; eco_s: number; count_s: number; trash_alert_s: number; passing_s: number; passing_cooldown_s: number
}
/** 「LIMBO가 지나갑니다」 때 한 번 트는 소리 (운영자가 TTS로 만들어 넣은 파일). 없으면 null */
export interface DisplaySound { file: string; type: string; url: string }
/**
 * 장면 ⑤ 문구 (display.json의 eco.text). 운영자가 준 것만 오고, 빠진 것은 ECO_TEXT.
 * negative_hint만 null로 줄을 없앨 수 있다
 */
export interface EcoWords { kicker: string; initial: string; positive: string; negative: string; negative_hint: string | null }
/** eco.enabled: 장면 ⑤ 나무를 순환에 넣을지 (예전 서버면 없음 → 넣음). eco.text: 장면 ⑤ 문구 (예전 서버면 없음) */
export interface DisplayContent {
  revision: string; message: string | null; schedule: DisplayEvent[]; slides: DisplaySlide[]; sound?: DisplaySound | null
  eco?: { enabled: boolean; text?: Partial<EcoWords> }; timing: DisplayTiming
}

/** 서버가 내용을 정하지 않았을 때(폴더 없음·처음부터 잘못됨)의 장면 길이. 서버 TIMING_DEFAULTS와 같다 */
export const DEFAULT_TIMING: DisplayTiming = { location_s: 40, slides_s: 30, eco_s: 15, count_s: 10, trash_alert_s: 10, passing_s: 8, passing_cooldown_s: 60 }

const text = (v: unknown) => typeof v === 'string'
const nullableText = (v: unknown) => v === null || typeof v === 'string'
const hhmm = (v: unknown) => typeof v === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(v)

/** 응답 검사. 모양이 다르면 null (받지 못한 것으로 보고 지난 내용을 그대로 쓴다) */
export function parseDisplayContent(value: unknown): DisplayContent | null {
  const c = value as DisplayContent
  if (!c || !text(c.revision) || !nullableText(c.message) || !Array.isArray(c.schedule) || !Array.isArray(c.slides) || !c.timing) return null
  if (!c.schedule.every(e => e && text(e.title) && hhmm(e.start) && (e.end === null || hhmm(e.end)) && nullableText(e.date) && nullableText(e.place))) return null
  // 그림 주소는 이 서버의 슬라이드 경로만 (다른 곳의 그림을 띄우지 않게)
  if (!c.slides.every(s => s && text(s.file) && text(s.url) && s.url.startsWith('/api/v1/display/slides/') && s.width > 0 && s.height > 0)) return null
  const sound = c.sound
  if (sound != null && (!text(sound.url) || !sound.url.startsWith('/api/v1/display/sound/') || !text(sound.type))) return null
  if (c.eco != null && typeof c.eco.enabled !== 'boolean') return null
  const words = c.eco?.text
  if (words != null && (typeof words !== 'object' || !Object.entries(words).every(([k, v]) =>
    k in ECO_TEXT && (text(v) || (k === 'negative_hint' && v === null))))) return null
  // eco_s는 예전 서버에 없으므로 기본값으로 채운다
  const timing = { ...c.timing, eco_s: c.timing.eco_s ?? DEFAULT_TIMING.eco_s }
  if (!(Object.keys(DEFAULT_TIMING) as (keyof DisplayTiming)[]).every(k => typeof timing[k] === 'number' && timing[k] > 0)) return null
  return { ...c, timing }
}

// ---- 어느 로봇을 보여 줄지 ----
/** 이 디스플레이가 붙은 로봇: 주소의 ?robot= → 없으면 서버 목록의 첫 로봇(기본 로봇) */
export function pickRobot(state: VisitorState | null, wanted: string | null): VisitorRobot | null {
  if (!state || state.robots.length === 0) return null
  if (wanted) return state.robots.find(r => r.robot_id === wanted) ?? null
  return state.robots[0]
}

// ---- 장면 ① 문구 ----
const LETTER_WITH_FINAL = new Set(['L', 'M', 'N', 'R'])           // 엘·엠·엔·알
const DIGIT_WITH_FINAL = new Set(['0', '1', '3', '6', '7', '8'])  // 영·일·삼·육·칠·팔

/** 주어 조사 은/는. 한글은 받침으로, 숫자·영문 끝은 읽는 소리로 (LIMBO-01 → 은, LIMBO-02 → 는) */
export function topic(word: string) {
  const last = word.trim().slice(-1)
  if (!last) return word
  const code = last.charCodeAt(0)
  let final: boolean
  if (code >= 0xac00 && code <= 0xd7a3) final = (code - 0xac00) % 28 !== 0
  else if (/[0-9]/.test(last)) final = DIGIT_WITH_FINAL.has(last)
  else if (/[A-Za-z]/.test(last)) final = LETTER_WITH_FINAL.has(last.toUpperCase())
  else return `${word}은(는)`
  return word + (final ? '은' : '는')
}

export interface LocationText {
  title: string           // 크게: "복도에 있어요"
  detail: string | null   // 작게: "201 강의실 쪽으로 가는 중" / "마지막으로 확인한 곳: 복도"
  badge: string | null    // 상태 알약: "순찰 중"
}

/**
 * 장면 ①의 큰 문구. 모르는 것은 지어내지 않는다 (PRD v0.3: 구역 밖이면 일반 문구, 오래된 위치는 「마지막으로 확인한 곳」).
 * problem: 서버에서 새 상태를 받지 못하고 있음 (가지고 있는 상태는 오래됨)
 */
export function locationText(robot: VisitorRobot | null, problem: boolean): LocationText {
  if (!robot) return { title: problem ? '정보를 받을 수 없어요' : '정보를 불러오고 있어요', detail: null, badge: null }
  const fresh = robot.position !== null && !robot.position.stale
  const area = robot.area ?? null
  const last = area ? `마지막으로 확인한 곳: ${area}` : null
  if (problem) return { title: '지금 위치를 확인할 수 없어요', detail: last, badge: null }
  if (robot.status === 'offline') return { title: '연결이 끊겼어요', detail: last, badge: visitorStatus.offline.label }
  if (robot.status === 'checking') return { title: '상태를 확인하고 있어요', detail: last, badge: visitorStatus.checking.label }
  const badge = visitorStatus[robot.status].label
  if (!fresh) {
    const title = robot.status === 'patrolling' ? '행사장을 돌고 있어요' : robot.status === 'paused' ? '잠시 멈춰 있어요' : '쉬고 있어요'
    return { title, detail: last, badge }
  }
  if (robot.status === 'patrolling') {
    const next = robot.next_area ?? null
    const title = area ? `${area}에 있어요` : '행사장을 돌고 있어요'
    const detail = next ? (next === area ? `${area} 안을 순찰하는 중` : `${next} 쪽으로 가는 중`) : '순찰 경로를 따라 가는 중'
    return { title, detail, badge }
  }
  if (robot.status === 'paused') return { title: area ? `${area}에서 잠시 멈췄어요` : '잠시 멈춰 있어요', detail: null, badge }
  return { title: area ? `${area}에서 쉬고 있어요` : '쉬고 있어요', detail: null, badge }
}

/** 큰 문구 글자 크기 단계 (1920×1080 기준 px). 긴 구역 이름도 한두 줄 안에 들게 */
export function titleSize(title: string) {
  const n = [...title].length
  return n <= 9 ? 120 : n <= 14 ? 96 : n <= 20 ? 76 : 60
}

// ---- 행사 일정 ----
export type EventState = 'past' | 'now' | 'next' | 'later'
export interface ShownEvent { event: DisplayEvent; state: EventState }

const pad = (n: number) => String(n).padStart(2, '0')
export const localDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const localTime = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`

/**
 * 보여 줄 일정 3건: 지금 진행 중인 행사가 있으면 지난 것·지금·다음, 없으면 다음 행사를 가운데에.
 * 날짜가 없는 일정은 매일. 오늘 일정이 없으면 다가오는 날의 일정(날짜와 함께). 시각은 이 화면(키오스크)의 시계 기준.
 */
export function pickEvents(schedule: DisplayEvent[], now: Date, count = 3): ShownEvent[] {
  const today = localDate(now), time = localTime(now)
  const todays = schedule.filter(e => e.date === null || e.date === today).sort((a, b) => a.start.localeCompare(b.start))
  if (todays.length) {
    const stateOf = (e: DisplayEvent): EventState =>
      e.start <= time && e.end !== null && time < e.end ? 'now' : e.start > time ? 'next' : 'past'
    const states = todays.map(stateOf)
    let center = states.indexOf('now')
    if (center < 0) center = states.indexOf('next')
    if (center >= 0) {
      let start = Math.max(0, center - 1)
      start = Math.max(0, Math.min(start, todays.length - count))
      return todays.slice(start, start + count).map((event, i) => ({ event, state: states[start + i] }))
    }
  }
  // 오늘 행사가 없거나 다 끝났으면 다가오는 날의 일정
  const later = schedule.filter(e => e.date !== null && e.date > today)
    .sort((a, b) => (a.date! + a.start).localeCompare(b.date! + b.start))
  return later.slice(0, count).map(event => ({ event, state: 'later' }))
}

// ---- 회전 규칙 R ----
export type SceneKey = 'location' | 'slides' | 'eco' | 'count'
export interface Slot { scene: SceneKey; seconds: number }

/**
 * 시간 순환 칸: ① → ② → ① → ⑤(나무) → ③(오늘 받은 횟수). 보여 줄 것이 없는 칸은 뺀다
 * (팜플렛이 없으면 ②, display.json에서 나무를 껐으면 ⑤, 쓰레기 받음 신호가 아직 없으면 ③). ①만 남으면 한 칸.
 */
export function rotationPlan(timing: DisplayTiming, slideCount: number, hasCount: boolean, hasEco = false): Slot[] {
  const location: Slot = { scene: 'location', seconds: timing.location_s }
  const slots: Slot[] = [location]
  if (slideCount > 0) slots.push({ scene: 'slides', seconds: timing.slides_s })
  if (slideCount > 0 || hasCount) slots.push(location)
  if (hasEco) slots.push({ scene: 'eco', seconds: timing.eco_s })
  if (hasCount) slots.push({ scene: 'count', seconds: timing.count_s })
  return slots
}

/** 순환 위치: 칸 번호, 그 칸을 시작한 시각(ms), 몇 바퀴째(팜플렛은 바퀴마다 다음 장) */
export interface Rotation { slot: number; startedAt: number; round: number }

/**
 * now(ms)에 보일 칸으로 넘긴다. locked면 ①에 머문다(로봇 연결 끊김·대기 중: PRD v0.3 R 「① 고정」).
 * 칸 구성이 바뀌어 번호가 넘치면 처음부터. 화면이 오래 멈췄다 깨어나면(탭 숨김 등) 지금부터 다시 센다.
 */
export function advance(r: Rotation, plan: Slot[], now: number, locked: boolean): Rotation {
  // 고정 중에는 ①의 처음에 붙잡아 두고, 풀리면 ①부터 제 길이만큼 다시 보여 준다
  if (locked || plan.length === 0) return { slot: 0, startedAt: now, round: r.round }
  let { slot, startedAt, round } = r
  if (slot >= plan.length) { slot = 0; startedAt = now }
  const cycle = plan.reduce((sum, s) => sum + s.seconds, 0) * 1000
  if (now - startedAt > cycle) return { slot: 0, startedAt: now, round: round + 1 }
  while (now - startedAt >= plan[slot].seconds * 1000) {
    startedAt += plan[slot].seconds * 1000
    slot += 1
    if (slot === plan.length) { slot = 0; round += 1 }
  }
  return slot === r.slot && startedAt === r.startedAt && round === r.round ? r : { slot, startedAt, round }
}

/** 로봇 상태가 ① 고정 조건인가 */
export const locksRotation = (robot: VisitorRobot | null) => robot !== null && (robot.status === 'offline' || robot.status === 'idle')

// ---- 장면 ④ 「LIMBO가 지나갑니다」 ----
/**
 * lastMoving: 지난번에 본 움직임 (처음·모름은 null), until: 오버레이를 내릴 시각(ms), lastAt: 마지막으로 띄운 시각(ms)
 */
export interface Passing { lastMoving: boolean | null; until: number | null; lastAt: number | null }
export const NO_PASSING: Passing = { lastMoving: null, until: null, lastAt: null }

/**
 * 순찰 중에 멈춰 있다가 움직이기 시작하면(false → true) passing_s 동안 띄운다. 띄운 뒤 passing_cooldown_s 안에는 다시 띄우지 않는다.
 * 화면을 켰을 때 이미 움직이던 것(처음 본 값)이나 모름(null)에서 바뀐 것은 출발로 보지 않는다.
 * 서버와 끊기거나 순찰 중이 아니면 바로 내린다 (지금 움직이는지 모르므로).
 */
export function passingStep(p: Passing, robot: VisitorRobot | null, problem: boolean, now: number, timing: DisplayTiming): Passing {
  if (problem || !robot || robot.status !== 'patrolling') {
    const next = { lastMoving: null, until: null, lastAt: p.lastAt }
    return p.lastMoving === null && p.until === null ? p : next
  }
  const moving = robot.moving ?? null
  let { until, lastAt } = p
  const cooled = lastAt === null || now - lastAt >= timing.passing_cooldown_s * 1000
  if (moving === true && p.lastMoving === false && cooled) {
    until = now + timing.passing_s * 1000
    lastAt = now
  }
  if (until !== null && now >= until) until = null
  return moving === p.lastMoving && until === p.until && lastAt === p.lastAt ? p : { lastMoving: moving, until, lastAt }
}

/** 오버레이 문구. 어디서 어디로 가는지는 아는 만큼만 */
export function passingText(robot: VisitorRobot | null) {
  const area = robot?.area ?? null, next = robot?.next_area ?? null
  // 같은 구역 안에서 움직이면 방향은 말하지 않는다 (「복도에서 복도 쪽으로」가 되지 않게)
  const way = !next || next === area ? null : area ? `${area} → ${next} 쪽으로` : `${next} 쪽으로 가요`
  return { title: 'LIMBO가 지나갑니다', detail: way ? `${way} · 길을 조금 비켜 주세요` : '길을 조금 비켜 주세요' }
}

/** 소리 파일이 없을 때 브라우저 음성으로 읽을 문장 (LIMBO를 영어 철자로 읽지 않게 한글로) */
export const PASSING_SPEECH = '림보가 지나갑니다. 길을 조금 비켜 주세요.'

// ---- 장면 ⑤ 환경 피드백: 나무 3상태 ----
/** 확인 방법별로 화면에 밝히는 말. 사람이 검수한 것처럼 쓰지 않는다 (PRD v0.3.2: AI 확인은 「AI 확인」) */
const METHOD_LABEL: Record<string, string> = {
  ai_bin_inspection: 'AI 확인', human_audit: '직접 확인', sensor_verified: '센서 확인', verified_route_log: '기록 확인',
}

/** 장면 ⑤ 기본 문구. 부정은 부드럽게: 탓하거나 겁주지 않고 다음에 할 일을 알려 준다 (PRD v0.3.2). 수거함은 일반/재활용 두 칸 */
export const ECO_TEXT: EcoWords = {
  kicker: '우리가 함께 키우는 나무',
  initial: '분리수거 결과를 모으는 중이에요',
  positive: '분리수거를 잘하고 있어요!',
  negative: '분리수거가 잘 안 되고 있어요',
  negative_hint: '재활용할 수 있는 것은 재활용 칸, 나머지는 일반 칸에 넣어 주세요',
}

export interface EcoText {
  tree: EcoTree
  kicker: string           // 제목 위 작은 줄
  title: string            // 크게
  detail: string | null    // 작게: "수거함을 비운 뒤 · AI 확인 20건 중 18건 바르게" (판정이 됐을 때만)
  hint: string | null      // 부정일 때 다음에 무엇을 하면 되는지
}

/**
 * 나무 그림과 문구. 판정은 서버가 하고 화면은 state만 본다(성공률을 다시 계산하지 않음).
 * 판정이 없거나(서버와 끊김·예전 서버·이상한 값) initial이면 숫자 없이 초기 나무.
 * 문구는 display.json의 eco.text(words), 빠진 것은 ECO_TEXT. 숫자 줄(detail)은 판정값으로 만든다
 */
export function ecoText(eco: EcoView | null | undefined, words?: Partial<EcoWords>): EcoText {
  const w = { ...ECO_TEXT, ...words }
  if (!eco || eco.state === 'initial' || eco.total == null || eco.correct == null) {
    return { tree: 'initial', kicker: w.kicker, title: w.initial, detail: null, hint: null }
  }
  const how = METHOD_LABEL[eco.method ?? ''] ?? '확인'
  const detail = `수거함을 비운 뒤 · ${how} ${eco.total}건 중 ${eco.correct}건 바르게`
  if (eco.state === 'positive') return { tree: 'positive', kicker: w.kicker, title: w.positive, detail, hint: null }
  return { tree: 'negative', kicker: w.kicker, title: w.negative, detail, hint: w.negative_hint }
}

/** 데모 나무: 바퀴마다 초기 → 긍정 → 부정 */
export function demoEco(round: number): EcoView {
  const tree = (['initial', 'positive', 'negative'] as const)[round % 3]
  if (tree === 'initial') return { state: 'initial' }
  return tree === 'positive'
    ? { state: 'positive', rate_percent: 90, correct: 18, total: 20, method: 'ai_bin_inspection' }
    : { state: 'negative', rate_percent: 65, correct: 13, total: 20, method: 'ai_bin_inspection' }
}

// ---- 데모 (/display?demo): 서버 없이 ----
const minutes = (d: Date, delta: number) => localTime(new Date(d.getTime() + delta * 60000))

/** 지금 시각 앞뒤로 만든 예시 일정 (지난 것·지금·다음이 늘 보이게) + 팜플렛 예시 2장 */
export function demoDisplayContent(now = new Date()): DisplayContent {
  const slide = (n: number, color: string) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="${color}"/>`
      + `<text x="960" y="500" font-size="96" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#14532d">행사장 팜플렛 예시 ${n}/2</text>`
      + `<text x="960" y="620" font-size="48" font-family="sans-serif" text-anchor="middle" fill="#14532d">운영자가 1920×1080 그림으로 바꿔 넣습니다</text></svg>`
    return { file: `demo-${n}.svg`, width: 1920, height: 1080, type: 'image/svg+xml', url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}` }
  }
  const start = new Date(now)
  // 자정 근처에서도 오늘 안에 들게 (예시라 정확한 시각은 중요하지 않음)
  if (now.getHours() === 0 && now.getMinutes() < 40) start.setMinutes(40)
  if (now.getHours() === 23 && now.getMinutes() > 19) start.setMinutes(19)
  return {
    revision: 'demo', message: '쓰레기는 LIMBO에게 주세요.',
    schedule: [
      { date: null, start: minutes(start, -40), end: minutes(start, -10), title: '개회', place: null },
      { date: null, start: minutes(start, -10), end: minutes(start, 20), title: 'LIMBO 데모', place: '주행사장' },
      { date: null, start: minutes(start, 20), end: minutes(start, 40), title: 'Q&A', place: null },
    ],
    slides: [slide(1, '#dcfce7'), slide(2, '#fef3c7')],
    sound: null,                                                   // 서버에 소리 파일이 있으면 useDisplayData가 채운다 (없으면 브라우저 한국어 음성)
    eco: { enabled: true },                                        // 나무는 바퀴마다 초기 → 긍정 → 부정 (demoEco)
    timing: { ...DEFAULT_TIMING, location_s: 12, slides_s: 8, eco_s: 8, passing_s: 5, passing_cooldown_s: 20 },   // 데모는 짧게 돌아 금방 볼 수 있게
  }
}
