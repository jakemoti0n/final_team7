import { expect, it } from 'vitest'
import { moveBy } from './GuideCanvas'
import {
  contentBox, emptyGuide, guideProblems, labelFit, labelPoint, nameProblem, nextCategoryKey, nextName, normalized,
  pointInPolygon, rectangle, simplePolygon, snap, snapPoint, type Guide, type Point,
} from './guide'

const map = { resolution: .05, origin: [-10, -10, 0], width: 680, height: 560, image: null, waypoints: [] }

it('new guide: default categories and bounds 10 m wider than the map', () => {
  const g = emptyGuide(map, 'm.yaml')
  expect(g.bounds).toEqual({ x_min: -20, y_min: -20, x_max: 34, y_max: 28 })
  expect(g.categories.map(c => c.label).slice(0, 4)).toEqual(['강의실', '행사장', '화장실', '입구'])
  expect(g.map).toBe('m.yaml')
})

it('snapping: 0.25 m grid, 5 cm when fine', () => {
  expect(snap(1.13)).toBe(1.25); expect(snap(-0.12)).toBe(0); expect(snap(1.13, .05)).toBe(1.15)
  expect(snapPoint([0.37, -2.62])).toEqual([0.25, -2.5])
})

it('rectangle from any two corners is counter-clockwise', () => {
  expect(rectangle([3, 4], [1, 2])).toEqual([[1, 2], [3, 2], [3, 4], [1, 4]])
})

it('polygon rules match the server: no crossing, no repeated point, has area', () => {
  expect(simplePolygon([[0, 0], [4, 0], [4, 4], [0, 4]])).toBe(true)
  expect(simplePolygon([[0, 0], [4, 4], [4, 0], [0, 4]])).toBe(false)      // 나비 모양
  expect(simplePolygon([[0, 0], [2, 0], [4, 0]])).toBe(false)              // 넓이 없음
  expect(simplePolygon([[0, 0], [2, 0], [2, 2], [2, 0]])).toBe(false)      // 같은 점
  expect(simplePolygon([[0, 0], [2, 0]])).toBe(false)
})

it('label sits inside even for a U shape', () => {
  const u: Point[] = [[0, 0], [6, 0], [6, 6], [4, 6], [4, 2], [2, 2], [2, 6], [0, 6]]
  const p = labelPoint(u)
  expect(pointInPolygon(p, u)).toBe(true)
  expect(labelPoint([[0, 0], [4, 0], [4, 2], [0, 2]])).toEqual([2, 1])
})

it('label text shrinks to fit and hides in tiny areas; icon goes first when short', () => {
  const room = rectangle([0, 0], [4, 3])
  const big = labelFit(room, '201 강의실')
  expect(big.showText).toBe(true)
  expect(big.size * 5.4).toBeLessThanOrEqual(4 * .9 + 1e-9)               // 한글 3 + 숫자·공백 4×0.6 = 5.4 글자폭
  expect(labelFit(rectangle([0, 0], [1, .3]), '아주 긴 이름의 강의실').showText).toBe(false)
  const flat = labelFit(rectangle([0, 0], [8, .8]), '복도')
  expect(flat.showText).toBe(true); expect(flat.showIcon).toBe(false)
})

it('names: 1–32 characters, no control characters', () => {
  expect(nameProblem('정문')).toBeNull()
  expect(nameProblem('  ')).not.toBeNull()
  expect(nameProblem('가'.repeat(33))).not.toBeNull()
  expect(nameProblem('a\nb')).not.toBeNull()
  expect(nextName('새 구역', ['새 구역 1', '새 구역 2'])).toBe('새 구역 3')
  expect(nextName('새 구역', ['새 구역 2'])).toBe('새 구역 3')        // 개수+1부터 찾으므로 겹치면 건너뛴다
  expect(nextCategoryKey([{ key: 'custom-1', label: 'a', color: '#FFFFFF', icon: 'none' }])).toBe('custom-2')
})

function sample(): Guide {
  const g = emptyGuide(map, 'm.yaml')
  g.areas = [{ name: '방', category: 'classroom', polygon: rectangle([0, 0], [4, 3]) }]
  g.markers = [{ name: '정문', category: 'entrance', x: 33.9, y: 0 }]
  return g
}

it('problems before saving: unknown category, crossing edges, outside bounds, bad name', () => {
  expect(guideProblems(sample())).toEqual([])
  const g = sample()
  g.areas.push({ name: '나비', category: 'classroom', polygon: [[0, 0], [4, 4], [4, 0], [0, 4]] })
  g.areas.push({ name: '밖', category: 'nope', polygon: rectangle([30, 0], [40, 3]) })
  g.markers.push({ name: ' ', category: 'entrance', x: 0, y: 0 })
  const problems = guideProblems(g)
  expect(problems.some(p => p.includes('나비') && p.includes('엇갈'))).toBe(true)
  expect(problems.some(p => p.includes('밖') && p.includes('없는 종류'))).toBe(true)
  expect(problems.some(p => p.includes('밖') && p.includes('영역 밖'))).toBe(true)
  expect(problems.some(p => p.includes('표시점') && p.includes('1~32'))).toBe(true)
})

it('normalized: trims names, rounds to mm, upper-case colors', () => {
  const g = sample()
  g.areas[0].name = ' 방 '; g.markers[0].x = 1.23456; g.categories[0].color = '#abcdef'
  const n = normalized(g)
  expect(n.areas[0].name).toBe('방'); expect(n.markers[0].x).toBe(1.235); expect(n.categories[0].color).toBe('#ABCDEF')
})

it('moving by arrow keys stays inside the drawing area', () => {
  const g = sample()
  expect(moveBy(g, { kind: 'area', index: 0 }, [0.25, 0]).areas[0].polygon[0]).toEqual([0.25, 0])
  expect(moveBy(g, { kind: 'marker', index: 0 }, [1, 0]).markers[0].x).toBe(34)        // 영역 끝에서 멈춤
  const edge = { ...g, areas: [{ ...g.areas[0], polygon: rectangle([30, 0], [34, 3]) }] }
  expect(moveBy(edge, { kind: 'area', index: 0 }, [0.25, 0])).toBe(edge)              // 넘어가면 그대로
})

it('content box covers areas and markers', () => {
  expect(contentBox(sample())).toEqual({ x_min: 0, y_min: 0, x_max: 33.9, y_max: 3 })
  expect(contentBox(emptyGuide(map, null))).toBeNull()
})

// ---- 그림 약도 ----
import { addPick, completePairs } from './Calibration'
import { placeImage } from './MainImage'
import { applyTransform, boundsCovering, fitTransform, imageCorners, matchTemplate, svgMatrix, templateSize, templateTransform, type Transform } from './guide'

it('template: 1 m = ppm px from the top-left of the drawing area', () => {
  const b = { x_min: -20, y_min: -20, x_max: 34, y_max: 28 }
  expect(templateSize(b, 20)).toEqual([1080, 960])
  const t = templateTransform(b, 20)
  expect(applyTransform(t, [0, 0])).toEqual([-20, 28])
  expect(applyTransform(t, [1080, 960])).toEqual([34, -20])
  expect(matchTemplate(b, 1080, 960)).toBe(20); expect(matchTemplate(b, 2161, 1920)).toBe(40); expect(matchTemplate(b, 900, 1230)).toBeNull()
})

it('fits rotation + scale + shift exactly from 3 or more points, and reports error', () => {
  // 90° 돌리고 1/60로 줄이고 옮긴 그림 (실제 지도로 만든 시험 그림과 같은 변환)
  const truth: Transform = [0, -1 / 60, 18, -1 / 60, 0, 10.5]
  const pairs = [[90, 1080], [120, 120], [810, 150], [840, 990]].map(p => ({ image: p as [number, number], map: applyTransform(truth, p as [number, number]) }))
  const fit = fitTransform(pairs)!
  fit.transform.forEach((v, i) => expect(v).toBeCloseTo(truth[i], 9))
  expect(fit.rms).toBeLessThan(1e-9)
  const noisy = pairs.map((p, i) => i === 0 ? { ...p, map: [p.map[0] + 0.4, p.map[1]] as [number, number] } : p)
  const rough = fitTransform(noisy)!
  // 점이 4개뿐이면 한 점의 오차가 여러 점에 나뉘어 보이므로, 평균 어긋남이 생기는 것만 본다
  expect(rough.rms).toBeGreaterThan(0.05); expect(rough.rms).toBeLessThan(0.4)
  expect(fitTransform(pairs.slice(0, 2))).toBeNull()
  expect(fitTransform([{ image: [0, 0], map: [0, 0] }, { image: [1, 1], map: [1, 1] }, { image: [2, 2], map: [2, 2] }])).toBeNull()   // 한 줄
})

it('svg matrix places image pixels at map metres with y flipped', () => {
  const t: Transform = [0.1, 0, -5, 0, -0.1, 15]
  expect(svgMatrix(t)).toBe('matrix(0.1 0 0 0.1 -5 -15)')
  expect(imageCorners({ transform: t, width: 100, height: 50 })).toEqual([[-5, 15], [5, 15], [5, 10], [-5, 10]])
})

it('bounds widen to cover an image placed outside, with a 1 m margin', () => {
  const b = { x_min: 0, y_min: 0, x_max: 10, y_max: 10 }
  expect(boundsCovering(b, [[2, 2], [8, 8]])).toEqual(b)
  expect(boundsCovering(b, [[-3.2, 2], [12.5, 11]])).toEqual({ x_min: -5, y_min: 0, x_max: 14, y_max: 12 })
  const g = { ...emptyGuide(map, 'm.yaml'), bounds: b }
  const placed = placeImage(g, { file: 'image-0000000000000000.png', width: 100, height: 100 }, [], [0.2, 0, -5, 0, -0.2, 20])
  expect(placed.widened).toBe(true)
  expect(guideProblems(placed.guide)).toEqual([])
})

it('control point pairs fill the first open slot on either side', () => {
  let pairs = addPick([], 'image', [1, 1])
  pairs = addPick(pairs, 'image', [2, 2])                 // 그림 점 둘 먼저
  pairs = addPick(pairs, 'map', [10, 10])                 // 첫 짝에 지도 점
  expect(pairs).toEqual([{ image: [1, 1], map: [10, 10] }, { image: [2, 2] }])
  expect(completePairs(pairs)).toEqual([{ image: [1, 1], map: [10, 10] }])
  expect(addPick(pairs, 'map', [20, 20])[1]).toEqual({ image: [2, 2], map: [20, 20] })
})

it('an image outside the drawing area is a problem before saving', () => {
  const g = emptyGuide(map, 'm.yaml')
  g.image = { file: 'image-0000000000000000.png', width: 100, height: 100, transform: [1, 0, 0, 0, -1, 0], points: [], show_areas: false }
  expect(guideProblems(g).some(p => p.includes('그림'))).toBe(true)
})
