import { test, expect, type Page } from '@playwright/test'
import { existsSync } from 'node:fs'

// 시험 서버(config.json)의 약도 파일. 실제 서버 시험은 API를 가로채므로 이 파일을 만들지 않아야 한다
const repoGuide = new URL('../../guides/human_test_map_guide.yaml', import.meta.url)

test.use({ viewport: { width: 1400, height: 1300 } })   // 그리기 판이 화면 안에 다 보이게

async function canvasPoint(page: Page, fx: number, fy: number) {
  await page.getByTestId('guide-canvas').scrollIntoViewIfNeeded()
  const box = (await page.getByTestId('guide-canvas').boundingBox())!
  return [box.x + box.width * fx, box.y + box.height * fy] as const
}
async function drag(page: Page, from: [number, number], to: [number, number]) {
  const [x1, y1] = await canvasPoint(page, ...from), [x2, y2] = await canvasPoint(page, ...to)
  await page.mouse.move(x1, y1); await page.mouse.down()
  await page.mouse.move(x2, y2, { steps: 6 }); await page.mouse.up()
}
const selected = (page: Page) => page.getByRole('region', { name: '고른 항목' })

test('demo guide: draw, rename, reshape, undo, preview and save without API calls', async ({ page }) => {
  const apiRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })
  await page.goto('/demo?page=guide')
  await expect(page.getByRole('heading', { name: '약도 편집' })).toBeVisible()
  await expect(page.getByTestId('guide-area')).toHaveCount(4)                  // 데모 예시 구역
  await expect(page.getByTestId('guide-status')).toHaveText('저장된 약도와 같습니다')
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeDisabled()

  // 사각형 그리기 → 이름·종류 정하기
  await page.getByRole('radio', { name: '사각형' }).click()
  await drag(page, [.30, .80], [.45, .92])
  await expect(page.getByTestId('guide-area')).toHaveCount(5)
  await selected(page).getByLabel('이름', { exact: true }).fill('학생 휴게실')
  await selected(page).getByLabel('이름', { exact: true }).press('Enter')
  await selected(page).getByLabel('종류', { exact: true }).selectOption({ label: '기타' })
  await expect(page.locator('[data-testid=guide-area][data-name="학생 휴게실"]')).toHaveAttribute('fill', '#FFFFFF')
  await expect(page.getByTestId('guide-status')).toHaveText('저장하지 않은 변경이 있습니다')

  // 모양 바꾸기: 변 가운데 손잡이를 끌면 꼭짓점이 하나 는다
  await page.getByRole('radio', { name: '선택' }).click()
  await page.getByRole('region', { name: '구역 목록' }).getByRole('button', { name: /학생 휴게실/ }).click()
  await expect(page.getByTestId('guide-vertex')).toHaveCount(4)
  const mid = page.locator('.guide-mid').first()
  const m = (await mid.boundingBox())!
  await page.mouse.move(m.x + m.width / 2, m.y + m.height / 2); await page.mouse.down()
  await page.mouse.move(m.x + m.width / 2, m.y + m.height / 2 + 30, { steps: 4 }); await page.mouse.up()
  await expect(page.getByTestId('guide-vertex')).toHaveCount(5)
  await expect(selected(page)).toContainText('꼭짓점 5개')
  await page.getByRole('button', { name: '되돌리기' }).click()
  await expect(page.getByTestId('guide-vertex')).toHaveCount(4)
  await page.getByRole('button', { name: '다시 하기' }).click()
  await expect(page.getByTestId('guide-vertex')).toHaveCount(5)

  // 다각형: 점 셋을 찍고 Enter
  await page.getByRole('radio', { name: '다각형' }).click()
  for (const [fx, fy] of [[.60, .82], [.75, .82], [.70, .94]] as const) { const [x, y] = await canvasPoint(page, fx, fy); await page.mouse.click(x, y) }
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('guide-area')).toHaveCount(6)
  // Delete 키로 지우기
  await page.keyboard.press('Delete')
  await expect(page.getByTestId('guide-area')).toHaveCount(5)

  // 표시점
  await page.getByRole('radio', { name: '표시점' }).click()
  const [px, py] = await canvasPoint(page, .5, .5); await page.mouse.click(px, py)
  await expect(page.getByTestId('guide-marker')).toHaveCount(3)

  // 미리보기: 지도 바탕·손잡이가 빠진다
  await page.getByLabel('방문자 미리보기').check()
  await expect(page.locator('.guide-vertex, .guide-grid')).toHaveCount(0)
  await page.getByLabel('방문자 미리보기').uncheck()

  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByTestId('guide-message')).toContainText('데모 약도에 반영했습니다')
  await expect(page.getByTestId('guide-status')).toHaveText('저장된 약도와 같습니다')
  expect(apiRequests).toEqual([])
})

test('leaving with unsaved guide changes asks first', async ({ page }) => {
  await page.goto('/demo?page=guide')
  await page.getByRole('radio', { name: '표시점' }).click()
  const [x, y] = await canvasPoint(page, .5, .5); await page.mouse.click(x, y)
  await expect(page.getByTestId('guide-status')).toHaveText('저장하지 않은 변경이 있습니다')
  const routes = page.getByRole('navigation', { name: '관제 메뉴' }).getByRole('link', { name: '순찰 경로' })
  page.once('dialog', dialog => { expect(dialog.message()).toContain('저장하지 않은 약도 변경'); void dialog.dismiss() })
  await routes.click()
  await expect(page).toHaveURL(/page=guide/)                                    // 머문다
  page.once('dialog', dialog => void dialog.accept())
  await routes.click()
  await expect(page).toHaveURL(/page=routes/)
})

test('live guide editor saves the whole guide with its revision and handles a conflict', async ({ page }) => {
  const existedBefore = existsSync(repoGuide)
  let serverGuide: unknown = null
  let revision = ''
  const puts: { revision: string; guide: { markers: { name: string; x: number; y: number }[] } }[] = []
  let conflictOnce = true
  await page.route('**/api/v1/guide', async route => {
    if (route.request().method() === 'GET') {
      const base = await (await route.fetch()).json()                            // 실제 서버의 빈 약도(또는 저장본) 형식을 그대로
      serverGuide ??= base.guide
      await route.fulfill({ json: { ...base, revision, exists: !!revision, guide: serverGuide } })
      return
    }
    const body = route.request().postDataJSON()
    puts.push(body)
    if (conflictOnce) {
      conflictOnce = false
      revision = 'someone-else'
      await route.fulfill({ status: 409, json: { error: { code: 'revision_conflict', message: 'Guide file changed; reload and try again' } } })
      return
    }
    serverGuide = body.guide; revision = `r${puts.length}`
    await route.fulfill({ json: { revision, exists: true, file: 'human_test_map_guide.yaml', guide: body.guide, map: 'human_test_map.yaml', map_matches: true, map_bounds: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 } } })
  })
  await page.goto('/?page=guide')
  await expect(page.getByTestId('guide-map')).toHaveAttribute('href', /map_sketch\.svg/)   // 바탕은 자동 약도
  await page.getByRole('radio', { name: '표시점' }).click()
  const [x, y] = await canvasPoint(page, .5, .5); await page.mouse.click(x, y)
  await selected(page).getByLabel('이름', { exact: true }).fill('정문')
  await selected(page).getByLabel('이름', { exact: true }).press('Enter')
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '먼저 저장되었습니다' })).toBeVisible()
  expect(puts[0].revision).toBe('')
  const marker = puts[0].guide.markers[0]
  expect(marker.name).toBe('정문')
  expect(Math.abs(marker.x * 4 - Math.round(marker.x * 4))).toBeLessThan(1e-9)    // 0.25 m 격자
  await page.getByRole('button', { name: '서버 약도 불러오기' }).click()
  await expect(page.getByTestId('guide-marker')).toHaveCount(0)                   // 서버 약도(빈 것)로 돌아감
  await page.mouse.click(x, y)
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByTestId('guide-message')).toContainText('저장했습니다')
  expect(puts[1].revision).toBe('someone-else')
  await expect(page.getByTestId('guide-status')).toHaveText('저장된 약도와 같습니다')
  expect(existsSync(repoGuide)).toBe(existedBefore)                               // 저장소 파일은 그대로
})

// ---- 그림 약도 ----
import { crc32, deflateSync } from 'node:zlib'

/** 회색 PNG (시험용) */
function png(width: number, height: number) {
  const chunk = (kind: string, body: Buffer) => {
    const head = Buffer.alloc(4); head.writeUInt32BE(body.length)
    const tail = Buffer.alloc(4); tail.writeUInt32BE(crc32(Buffer.concat([Buffer.from(kind), body])))
    return Buffer.concat([head, Buffer.from(kind), body, tail])
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = 0
  const rows = Buffer.alloc((width + 1) * height, 200)
  for (let y = 0; y < height; y++) rows[y * (width + 1)] = 0
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(rows)), chunk('IEND', Buffer.alloc(0))])
}
async function templateSize(page: Page) {
  const text = await page.getByRole('button', { name: /틀 내려받기/ }).first().textContent()
  const [, w, h] = text!.match(/(\d+)×(\d+)/)!
  return [Number(w), Number(h)]
}
/** 그림 판·지도 판의 좌표 → 화면 좌표 (지도는 m, y 뒤집음) */
async function boardPoint(page: Page, testid: string, x: number, y: number) {
  return page.getByTestId(testid).evaluate((svg, [px, py]) => {
    const q = new DOMPoint(px, py).matrixTransform((svg as SVGSVGElement).getScreenCTM()!)
    return [q.x, q.y] as [number, number]
  }, [x, y])
}

test('demo: an image drawn on the downloaded template fits by size; other sizes are refused', async ({ page }) => {
  await page.goto('/demo?page=guide')
  await page.getByLabel('그림 파일').check()
  const [w, h] = await templateSize(page)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: /틀 내려받기/ }).first().click()
  expect((await download).suggestedFilename()).toBe('limbo-guide-template-20pxm.png')
  await page.getByLabel('틀로 그린 그림 올리기').setInputFiles({ name: 'wrong.png', mimeType: 'image/png', buffer: png(w + 30, h) })
  await expect(page.getByTestId('guide-message')).toContainText('틀')
  await expect(page.getByTestId('guide-image')).toHaveCount(0)
  await page.getByLabel('틀로 그린 그림 올리기').setInputFiles({ name: 'drawn.png', mimeType: 'image/png', buffer: png(w, h) })
  await expect(page.getByTestId('guide-image')).toHaveCount(1)
  await expect(page.getByTestId('guide-image-info')).toContainText(`${w}×${h} px`)
  await expect(page.getByTestId('guide-image-info')).toContainText('틀 크기로 맞춤')
  // 방문자 미리보기: 그림만 (구역은 「그림 위에 구역도 보이기」를 켜야)
  await page.getByLabel('방문자 미리보기').check()
  await expect(page.getByTestId('guide-area')).toHaveCount(0)
  await page.getByLabel('방문자 미리보기').uncheck()
  await page.getByLabel('그림 위에 그린 구역도 보이기 (방문자 화면)').check()
  await page.getByLabel('방문자 미리보기').check()
  await expect(page.getByTestId('guide-area')).toHaveCount(4)
  await page.getByLabel('방문자 미리보기').uncheck()
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByTestId('guide-status')).toHaveText('저장된 약도와 같습니다')
})

test('demo: an existing guide image is placed with three control points', async ({ page }) => {
  await page.goto('/demo?page=guide')
  await page.getByLabel('그림 파일').check()
  await page.getByLabel('기준점으로 맞출 그림 올리기').setInputFiles({ name: 'plan.png', mimeType: 'image/png', buffer: png(200, 100) })
  await expect(page.getByRole('region', { name: '기준점으로 그림 맞추기' })).toBeVisible()
  await expect(page.getByRole('button', { name: '이대로 맞추기' })).toBeDisabled()
  // 1 px = 5 cm로 놓을 그림: (20,10)·(180,10)·(20,90) ↔ 지도 (-4,4.5)·(4,4.5)·(-4,0.5). 모서리는 「전체」 단추에 가릴 수 있어 안쪽 점
  const pairs: [[number, number], [number, number]][] = [[[20, 10], [-4, 4.5]], [[180, 10], [4, 4.5]], [[20, 90], [-4, 0.5]]]
  for (const [img, m] of pairs) {
    const [ix, iy] = await boardPoint(page, 'guide-image-board', ...img); await page.mouse.click(ix, iy)
    const [mx, my] = await boardPoint(page, 'guide-canvas', m[0], -m[1]); await page.mouse.click(mx, my)
  }
  await expect(page.getByTestId('guide-pair')).toHaveCount(3)
  await expect(page.getByTestId('guide-fit')).toContainText('평균 어긋남 0.0')
  await expect(page.getByTestId('guide-image')).toHaveCount(1)                   // 지도에 겹쳐 보기
  await page.getByRole('button', { name: '이대로 맞추기' }).click()
  await expect(page.getByTestId('guide-message')).toContainText('기준점 3개로 맞췄습니다')
  await expect(page.getByTestId('guide-image-info')).toContainText('기준점 3개로 맞춤')
  // 다시 맞추기를 열면 찍었던 점이 그대로
  await page.getByRole('button', { name: '기준점으로 다시 맞추기' }).click()
  await expect(page.getByTestId('guide-pair')).toHaveCount(3)
  await page.getByRole('button', { name: '취소' }).click()
  await page.getByRole('button', { name: '그림 빼기' }).click()
  await expect(page.getByTestId('guide-image')).toHaveCount(0)
})

test('live: the image is uploaded as-is and the guide refers to it by the returned name', async ({ page }) => {
  let uploaded: { type?: string; size: number } | null = null
  let saved: { guide: { image: { file: string; width: number; transform: number[] } } } | null = null
  await page.route('**/api/v1/guide', async route => {
    if (route.request().method() === 'GET') { await route.fulfill({ response: await route.fetch() }); return }
    saved = route.request().postDataJSON()
    const base = await (await route.fetch({ method: 'GET' })).json()
    await route.fulfill({ json: { ...base, revision: 'r1', exists: true, guide: saved!.guide } })
  })
  const file = 'image-0123456789abcdef.png'
  await page.goto('/?page=guide')
  await page.getByLabel('그림 파일').check()
  const [w, h] = await templateSize(page)
  const image = png(w, h)
  await page.route(`**/api/v1/guide/image/${file}`, route => route.fulfill({ body: image, contentType: 'image/png' }))
  // 업로드는 가로채서 저장소 폴더에 그림을 만들지 않는다. 화면은 서버가 알려 준 이름·크기를 쓴다
  await page.route('**/api/v1/guide/image', async route => {
    uploaded = { type: route.request().headers()['content-type'], size: route.request().postDataBuffer()!.length }
    await route.fulfill({ status: 201, json: { file, width: w, height: h, type: 'image/png' } })
  })
  await page.getByLabel('틀로 그린 그림 올리기').setInputFiles({ name: 'drawn.png', mimeType: 'image/png', buffer: image })
  await expect(page.getByTestId('guide-image')).toHaveAttribute('href', `/api/v1/guide/image/${file}`)
  expect(uploaded).toEqual({ type: 'image/png', size: image.length })
  await page.getByRole('button', { name: '저장', exact: true }).click()
  await expect(page.getByTestId('guide-message')).toContainText('저장했습니다')
  expect(saved!.guide.image.file).toBe(file)
  expect(saved!.guide.image.width).toBe(w)
  expect(saved!.guide.image.transform[0]).toBeCloseTo(1 / 20)
  expect(existsSync(repoGuide)).toBe(false)
})
