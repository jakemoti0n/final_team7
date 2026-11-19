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
