import { describe, expect, it } from 'vitest'
import { demoVisitorState, operatingText, parseVisitorState, positionAge } from './visitor'

const good = {
  server_utc: '2026-11-16T00:00:00Z', operating: 1,
  map: { resolution: 1, origin: [0, 0, 0], width: 10, height: 10, image: '/api/v1/visitor/map.png' },
  robots: [{ robot_id: 'LIMBO-01', status: 'patrolling', position: { x: 2.5, y: 3.5, stale: false, age_s: 0 } },
    { robot_id: 'LIMBO-02', status: 'offline', position: null }],
}

describe('visitor state', () => {
  it('accepts the server shape and rejects anything else', () => {
    expect(parseVisitorState(good)).toEqual(good)
    expect(parseVisitorState({ ...good, map: null })).not.toBeNull()
    expect(parseVisitorState(null)).toBeNull()
    expect(parseVisitorState({ ...good, robots: [{ ...good.robots[0], status: 'moving' }] })).toBeNull()
    expect(parseVisitorState({ ...good, robots: [{ ...good.robots[0], position: { x: 'a', y: 1, stale: false, age_s: 0 } }] })).toBeNull()
    expect(parseVisitorState({ ...good, map: { ...good.map, width: 0 } })).toBeNull()
  })

  it('says unknown when it cannot reach the server', () => {
    const state = parseVisitorState(good)!
    expect(operatingText(state, false)).toBe('LIMBO 1대 운행 중')
    expect(operatingText({ ...state, operating: 0 }, false)).toBe('지금 운행 중인 LIMBO가 없습니다')
    expect(operatingText(state, true)).toBe('지금 운행 대수를 확인할 수 없습니다')
    expect(operatingText(null, false)).toBe('로봇 정보를 불러오는 중입니다')
    expect(operatingText(null, true)).toBe('로봇 정보를 받을 수 없습니다')
  })

  it('adds time since receipt to the position age', () => {
    expect(positionAge({ x: 0, y: 0, stale: false, age_s: 2 }, 3)).toBe(5)
    expect(positionAge({ x: 0, y: 0, stale: true, age_s: null }, 3)).toBeNull()
  })

  it('demo robot moves on a half-metre grid and stays valid', () => {
    const a = demoVisitorState(0), b = demoVisitorState(5)
    expect(parseVisitorState(a)).not.toBeNull()
    expect(a.robots[0].position).not.toEqual(b.robots[0].position)
    for (const p of [a, b].map(s => s.robots[0].position!)) expect([p.x * 2 % 1, p.y * 2 % 1]).toEqual([0, 0])
  })
})

// ---- 안내 약도 ----
import { asGuide, demoVisitorGuide, parseVisitorGuide } from './visitor'

it('visitor guide: accepts the server shape, rejects anything odd', () => {
  const ok = demoVisitorGuide()
  expect(parseVisitorGuide(ok)).toBe(ok)
  const withImage = { ...ok, image: { file: 'image-0123456789abcdef.png', width: 10, height: 10, transform: [1, 0, 0, 0, -1, 0], show_areas: false, url: '/api/v1/visitor/guide/image/image-0123456789abcdef.png' } }
  expect(parseVisitorGuide(withImage)).not.toBeNull()
  expect(parseVisitorGuide({ ...withImage, image: { ...withImage.image, url: 'https://elsewhere.example/x.png' } })).toBeNull()   // 다른 곳 그림
  expect(parseVisitorGuide({ ...ok, categories: [{ ...ok.categories[0], color: 'red;background:url(x)' }] })).toBeNull()
  expect(parseVisitorGuide({ ...ok, categories: [{ ...ok.categories[0], icon: 'rocket' }] })).toBeNull()
  expect(parseVisitorGuide({ ...ok, areas: [{ name: 'x', category: 'event', polygon: [[0, 0], [1, 1]] }] })).toBeNull()
  expect(parseVisitorGuide({ ...ok, markers: [{ name: 'x', category: 'event', x: 'a', y: 0 }] })).toBeNull()
  expect(parseVisitorGuide(null)).toBeNull()
})

it('visitor guide is drawn with the editor drawing (no control points)', () => {
  const g = asGuide({ ...demoVisitorGuide(), image: { file: 'image-0123456789abcdef.png', width: 10, height: 10, transform: [1, 0, 0, 0, -1, 0], show_areas: true, url: '/x' } })
  expect(g.image).toEqual({ file: 'image-0123456789abcdef.png', width: 10, height: 10, transform: [1, 0, 0, 0, -1, 0], points: [], show_areas: true })
  expect(g.areas.length).toBe(4)
})
