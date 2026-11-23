import { describe, expect, it } from 'vitest'
import {
  DEFAULT_TIMING, NO_PASSING, advance, demoDisplayContent, locationText, locksRotation, parseDisplayContent, passingStep, passingText,
  pickEvents, pickRobot, rotationPlan, titleSize, topic, type DisplayEvent, type Passing, type Rotation,
} from './display'
import { qrModules, qrPath } from './qr'
import { areaAt, demoVisitorState, parseVisitorState, type VisitorRobot, type VisitorState } from '../visitor/visitor'
import { demoGuide } from '../guide/demoGuide'

const robot = (change: Partial<VisitorRobot> = {}): VisitorRobot => ({
  robot_id: 'LIMBO-01', status: 'patrolling', position: { x: 1, y: 1, stale: false, age_s: 0 },
  area: '복도', next_area: '201 강의실', progress: { done: 3, total: 10 }, moving: true, ...change,
})

describe('location text (scene ①)', () => {
  it('says where the robot is and where it goes, without inventing anything', () => {
    expect(locationText(robot(), false)).toEqual({ title: '복도에 있어요', detail: '201 강의실 쪽으로 가는 중', badge: '순찰 중' })
    expect(locationText(robot({ next_area: '복도' }), false).detail).toBe('복도 안을 순찰하는 중')
    expect(locationText(robot({ next_area: null }), false).detail).toBe('순찰 경로를 따라 가는 중')
    expect(locationText(robot({ area: null }), false).title).toBe('행사장을 돌고 있어요')      // 구역 밖
    expect(locationText(robot({ status: 'paused' }), false)).toEqual({ title: '복도에서 잠시 멈췄어요', detail: null, badge: '잠시 멈춤' })
    expect(locationText(robot({ status: 'idle', area: null }), false).title).toBe('쉬고 있어요')
  })

  it('old or missing positions become "last seen", never the current place', () => {
    const stale = { x: 1, y: 1, stale: true, age_s: 30 }
    expect(locationText(robot({ status: 'offline', position: stale }), false)).toEqual({ title: '연결이 끊겼어요', detail: '마지막으로 확인한 곳: 복도', badge: '연결 끊김' })
    expect(locationText(robot({ position: stale }), false)).toEqual({ title: '행사장을 돌고 있어요', detail: '마지막으로 확인한 곳: 복도', badge: '순찰 중' })
    expect(locationText(robot({ position: null, area: null }), false).detail).toBeNull()
    // 서버에서 받지 못하는 중: 가진 상태가 오래됐으므로 상태 알약도 보이지 않는다
    expect(locationText(robot(), true)).toEqual({ title: '지금 위치를 확인할 수 없어요', detail: '마지막으로 확인한 곳: 복도', badge: null })
    expect(locationText(null, false).title).toBe('정보를 불러오고 있어요')
    expect(locationText(robot({ status: 'checking' }), false).title).toBe('상태를 확인하고 있어요')
  })

  it('picks the right particle and shrinks long titles', () => {
    expect(['LIMBO-01', 'LIMBO-02', 'LIMBO-10', 'LIMBO', 'ROBOT-L', '로봇', '림보', 'X_'].map(topic))
      .toEqual(['LIMBO-01은', 'LIMBO-02는', 'LIMBO-10은', 'LIMBO는', 'ROBOT-L은', '로봇은', '림보는', 'X_은(는)'])
    expect(titleSize('복도에 있어요')).toBe(120)
    expect(titleSize('제2공학관 대강당에 있어요')).toBeLessThan(120)
    expect(titleSize('가'.repeat(32) + '에서 잠시 멈췄어요')).toBe(60)
  })

  it('shows the robot from ?robot=, else the server default (first)', () => {
    const state = demoVisitorState(0)
    expect(pickRobot(state, null)?.robot_id).toBe('LIMBO-01')
    expect(pickRobot(state, 'LIMBO-03')?.robot_id).toBe('LIMBO-03')
    expect(pickRobot(state, 'NOPE')).toBeNull()
    expect(pickRobot(null, null)).toBeNull()
  })
})

describe('schedule', () => {
  const at = (hm: string, date = '2026-11-27') => new Date(`${date}T${hm}:00`)
  const e = (start: string, end: string | null, title: string, date: string | null = null): DisplayEvent => ({ date, start, end, title, place: null })
  const day = [e('14:00', '14:30', '개회'), e('14:30', '15:10', '데모'), e('15:10', '15:40', 'Q&A'), e('16:00', null, '폐회')]
  const shown = (now: Date, schedule = day) => pickEvents(schedule, now).map(x => `${x.event.title}:${x.state}`)

  it('centres on the running event, else on the next one', () => {
    expect(shown(at('14:40'))).toEqual(['개회:past', '데모:now', 'Q&A:next'])
    expect(shown(at('14:00'))).toEqual(['개회:now', '데모:next', 'Q&A:next'])       // 첫 행사 중이면 앞으로 3건
    expect(shown(at('13:00'))).toEqual(['개회:next', '데모:next', 'Q&A:next'])
    expect(shown(at('15:50'))).toEqual(['데모:past', 'Q&A:past', '폐회:next'])       // 끝에 가까우면 뒤에서 3건
    expect(shown(at('16:05'))).toEqual([])                                             // 다 끝남 (끝 시각 없는 행사는 「지금」으로 만들지 않음)
  })

  it('dated events only on their day, then upcoming days', () => {
    const schedule = [e('10:00', '11:00', '내일 행사', '2026-11-28'), e('09:00', null, '어제', '2026-11-26'), e('13:00', '14:00', '오늘', '2026-11-27')]
    expect(shown(at('12:00'), schedule)).toEqual(['오늘:next'])
    expect(shown(at('15:00'), schedule)).toEqual(['내일 행사:later'])
    expect(shown(at('12:00', '2026-11-29'), schedule)).toEqual([])
  })
})

describe('rotation rule R', () => {
  const s = 1000
  const run = (plan: ReturnType<typeof rotationPlan>, times: number[], locked = () => false) => {
    let r: Rotation = { slot: 0, startedAt: 0, round: 0 }
    return times.map(t => { r = advance(r, plan, t * s, locked()); return `${plan[r.slot].scene}#${r.slot}/${r.round}` })
  }

  it('① 40 s → ② 30 s → ① 40 s, slides only when there are any', () => {
    expect(rotationPlan(DEFAULT_TIMING, 2, false).map(x => `${x.scene}:${x.seconds}`)).toEqual(['location:40', 'slides:30', 'location:40'])
    expect(rotationPlan(DEFAULT_TIMING, 0, false).map(x => x.scene)).toEqual(['location'])
    expect(rotationPlan(DEFAULT_TIMING, 1, true).map(x => x.scene)).toEqual(['location', 'slides', 'location', 'count'])
    expect(rotationPlan(DEFAULT_TIMING, 0, true).map(x => x.scene)).toEqual(['location', 'location', 'count'])
    const plan = rotationPlan(DEFAULT_TIMING, 2, false)
    expect(run(plan, [0, 39, 40, 69, 70, 109, 110, 150])).toEqual(
      ['location#0/0', 'location#0/0', 'slides#1/0', 'slides#1/0', 'location#2/0', 'location#2/0', 'location#0/1', 'slides#1/1'])
  })

  it('stays on ① while locked and restarts ① when released', () => {
    const plan = rotationPlan(DEFAULT_TIMING, 1, false)
    let locked = false
    let r: Rotation = { slot: 0, startedAt: 0, round: 0 }
    r = advance(r, plan, 45 * s, locked)
    expect(r.slot).toBe(1)
    locked = true
    r = advance(r, plan, 50 * s, locked)
    expect(r).toEqual({ slot: 0, startedAt: 50 * s, round: 0 })
    r = advance(r, plan, 500 * s, locked)
    locked = false
    r = advance(r, plan, 520 * s, locked)
    expect(r.slot).toBe(0)                                   // 풀린 뒤 ①을 제 길이만큼
    r = advance(r, plan, 541 * s, locked)
    expect(r.slot).toBe(1)
  })

  it('resets after a long sleep and when the plan shrinks', () => {
    const plan = rotationPlan(DEFAULT_TIMING, 1, false)
    const r = advance({ slot: 1, startedAt: 0, round: 4 }, plan, 3600 * s, false)
    expect(r).toEqual({ slot: 0, startedAt: 3600 * s, round: 5 })
    const shrunk = advance({ slot: 2, startedAt: 0, round: 0 }, rotationPlan(DEFAULT_TIMING, 0, false), 10 * s, false)
    expect(shrunk.slot).toBe(0)
  })

  it('locks only for offline or idle robots', () => {
    expect(locksRotation(robot({ status: 'offline' }))).toBe(true)
    expect(locksRotation(robot({ status: 'idle' }))).toBe(true)
    expect(locksRotation(robot({ status: 'paused' }))).toBe(false)
    expect(locksRotation(robot({ status: 'checking' }))).toBe(false)
    expect(locksRotation(null)).toBe(false)
  })
})

describe('server shapes', () => {
  const content = { revision: 'r', message: null, schedule: [{ date: null, start: '14:00', end: null, title: '개회', place: null }],
    slides: [{ file: 'a.png', width: 1920, height: 1080, type: 'image/png', url: '/api/v1/display/slides/a.png?v=1' }], timing: DEFAULT_TIMING }

  it('accepts the display content and rejects odd shapes', () => {
    expect(parseDisplayContent(content)).toBe(content)
    expect(parseDisplayContent({ ...content, slides: [{ ...content.slides[0], url: 'https://elsewhere.example/a.png' }] })).toBeNull()
    expect(parseDisplayContent({ ...content, schedule: [{ ...content.schedule[0], start: '9:00' }] })).toBeNull()
    expect(parseDisplayContent({ ...content, timing: { ...DEFAULT_TIMING, location_s: 0 } })).toBeNull()
    expect(parseDisplayContent(null)).toBeNull()
    const sound = { file: 'passing.mp3', type: 'audio/mpeg', url: '/api/v1/display/sound/passing.mp3?v=1' }
    expect(parseDisplayContent({ ...content, sound })).not.toBeNull()
    expect(parseDisplayContent({ ...content, sound: { ...sound, url: 'https://elsewhere.example/a.mp3' } })).toBeNull()
  })

  it('visitor state accepts the new robot fields and rejects broken ones', () => {
    const state: VisitorState = { server_utc: 'now', operating: 1, map: null, guide: null, display: 'r', robots: [robot()] }
    expect(parseVisitorState(state)).not.toBeNull()
    expect(parseVisitorState({ ...state, robots: [{ robot_id: 'old', status: 'idle', position: null }] })).not.toBeNull()   // 예전 서버
    expect(parseVisitorState({ ...state, robots: [robot({ progress: { done: 11, total: 10 } })] })).toBeNull()
    expect(parseVisitorState({ ...state, robots: [robot({ area: 3 as unknown as string })] })).toBeNull()
    expect(parseVisitorState({ ...state, robots: [robot({ moving: 'yes' as unknown as boolean })] })).toBeNull()
  })

  it('demo data is valid and walks through the drawn areas', () => {
    const states = [0, 5, 20, 33, 48].map(t => demoVisitorState(t))
    states.forEach(s => expect(parseVisitorState(s)).not.toBeNull())
    expect(states.map(s => s.robots[0].area)).toContain('201 강의실')
    expect(states.map(s => s.robots[0].area)).toContain('복도')
    expect(demoVisitorState(1).robots[0].moving).toBe(false)     // 모서리에서 잠시 멈췄다
    expect(demoVisitorState(5).robots[0].moving).toBe(true)
    const c = demoDisplayContent(new Date('2026-11-27T14:00:00'))
    expect(pickEvents(c.schedule, new Date('2026-11-27T14:00:00')).map(x => x.state)).toEqual(['past', 'now', 'next'])
  })

  it('areaAt picks the smallest drawn area, like the server', () => {
    const areas = demoGuide().areas
    expect(areaAt(areas, 0, 0)).toBe('복도')
    expect(areaAt(areas, 3, 5)).toBe('201 강의실')
    expect(areaAt(areas, 0, -6)).toBeNull()
    const nested = [{ name: '큰 방', category: 'event', polygon: [[0, 0], [10, 0], [10, 10], [0, 10]] as [number, number][] },
      { name: '부스', category: 'other', polygon: [[2, 2], [4, 2], [4, 4], [2, 4]] as [number, number][] }]
    expect(areaAt(nested, 3, 3)).toBe('부스')
    expect(areaAt(nested, 8, 8)).toBe('큰 방')
  })
})

describe('QR code', () => {
  it('builds the version that fits, with finder patterns and quiet zone in the path', () => {
    expect(qrModules('https://limbo.example.com/visitor').length).toBe(29)      // 버전 3
    expect(qrModules('A').length).toBe(21)
    expect(qrModules('x'.repeat(213)).length).toBe(57)                          // 버전 10, 꽉 참
    expect(() => qrModules('x'.repeat(214))).toThrow(/too long/)
    const m = qrModules('https://limbo.example.com/visitor')
    // 왼쪽 위 찾기 패턴: 7칸 검은 테두리, 그 안 흰 테두리, 가운데 3×3
    expect(m[0].slice(0, 7).every(Boolean)).toBe(true)
    expect(m[1].slice(1, 6).some(Boolean)).toBe(false)
    expect(m[3].slice(2, 5).every(Boolean)).toBe(true)
    expect(m[7].slice(0, 8).some(Boolean)).toBe(false)                         // 흰 구분선
    expect(qrPath([[true, true, false, true]], 4)).toBe('M4 4h2v1h-2zM7 4h1v1h-1z')
    // 같은 주소는 늘 같은 그림 (화면이 다시 그려도 바뀌지 않음)
    expect(qrModules('https://a.example/visitor')).toEqual(qrModules('https://a.example/visitor'))
  })
})

describe('scene ④ passing', () => {
  const s = 1000
  // (초, 로봇 상태) 순서대로 넣고 그때마다 오버레이가 떠 있는지
  const run = (steps: [number, Partial<VisitorRobot> | null, boolean?][]) => {
    let p: Passing = NO_PASSING
    return steps.map(([t, change, problem]) => {
      p = passingStep(p, change === null ? null : robot(change), problem ?? false, t * s, DEFAULT_TIMING)
      return p.until !== null
    })
  }

  it('shows for 8 s when a patrolling robot starts moving, not when the page opens mid-move', () => {
    expect(run([[0, { moving: true }], [3, { moving: true }]])).toEqual([false, false])       // 켜자마자 이미 움직이던 중
    expect(run([[0, { moving: false }], [3, { moving: true }], [10, { moving: true }], [11, { moving: true }]]))
      .toEqual([false, true, true, false])                                                          // 3 s에 출발 → 11 s에 내림
    expect(run([[0, { moving: null }], [3, { moving: true }]])).toEqual([false, false])      // 모름 → 움직임은 출발로 보지 않음
  })

  it('waits 60 s before showing again (stop-and-go in a crowd)', () => {
    expect(run([[0, { moving: false }], [1, { moving: true }], [20, { moving: false }], [30, { moving: true }],
      [50, { moving: false }], [62, { moving: true }]])).toEqual([false, true, false, false, false, true])
  })

  it('only while patrolling and connected', () => {
    expect(run([[0, { moving: false, status: 'paused' }], [3, { moving: true, status: 'paused' }]])).toEqual([false, false])
    expect(run([[0, { moving: false }], [3, { moving: true }], [4, { moving: true }, true]])).toEqual([false, true, false])   // 서버와 끊김 → 내림
    expect(run([[0, { moving: false }], [3, null]])).toEqual([false, false])
  })

  it('says where it goes only as far as it knows', () => {
    expect(passingText(robot())).toEqual({ title: 'LIMBO가 지나갑니다', detail: '복도 → 201 강의실 쪽으로 · 길을 조금 비켜 주세요' })
    expect(passingText(robot({ area: null })).detail).toBe('201 강의실 쪽으로 가요 · 길을 조금 비켜 주세요')
    expect(passingText(robot({ next_area: '복도' })).detail).toBe('길을 조금 비켜 주세요')
    expect(passingText(null).detail).toBe('길을 조금 비켜 주세요')
  })
})
