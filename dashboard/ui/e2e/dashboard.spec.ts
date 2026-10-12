import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { mkdirSync } from 'node:fs'
import { commandNames, resultLabels, type Command, type Outcome } from '../src/commands'
function telemetry() {
  const at = new Date().toISOString()
  return { schema_version: 1, robot_id: 'LIMBO-01', bridge_session_id: randomUUID(), sequence: 1, sent_at: at, source_clock: 'ros_sim', topics: Object.fromEntries(['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'].map(key => [key, { header_stamp: { sec: 0, nanosec: 0 }, last_received_at: at, age_ms: 0, received_count: 1, receive_hz: 10 }])), motion: { linear_speed_mps: 0, angular_velocity_radps: 0, last_received_at: at, age_ms: 0 } }
}
test('actual controls stay disabled, zero is a measured value, and demo never talks to actual APIs', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetry() })
  await page.goto('/')
  await expect(page.locator('.speed strong')).toHaveText('0.00')
  await expect(page.locator('.movement')).toContainText('정지 상태')
  for (const name of ['원격 정지', '순찰 재개', '프로그램 재시작']) await expect(page.getByRole('button', { name, exact: true })).toBeDisabled()
  const before = await (await request.get('/api/v1/state')).json()
  const requests: string[] = []
  page.on('request', req => { if (req.url().includes('/api/')) requests.push(req.url()) })
  page.on('websocket', socket => requests.push(socket.url()))
  await page.goto('/demo')
  await expect(page.getByText('데모 데이터 · 실제 로봇을 제어하지 않습니다')).toBeVisible()
  await page.getByRole('button', { name: '원격 정지', exact: true }).click()
  await expect(page.locator('.result')).toContainText('정지 상태 확인됨')
  expect(requests).toEqual([])
  const after = await (await request.get('/api/v1/state')).json()
  expect(after.bridge.sequence).toBe(before.bridge.sequence)
  expect(after.alerts.some((a: { kind: string }) => a.kind === 'control')).toBe(false)
  await page.goto('/')
  await expect(page.locator('.result')).toHaveCount(0)
})
test('browser connection loss masks old current status and recovers full state', async ({ page, request }) => {
  const p = telemetry()
  await request.post('/api/v1/telemetry', { data: p })
  await page.goto('/')
  await expect(page.locator('.connection')).toContainText('연결됨')
  await page.context().setOffline(true)
  await expect(page.getByRole('alert')).toContainText('서버 상태를 갱신할 수 없습니다')
  await expect(page.locator('.connection')).toContainText('현재 확인 불가')
  await expect(page.locator('tbody')).not.toContainText('수신 중')
  await expect(page.locator('.speed')).toContainText('마지막 수신 값')
  await page.context().setOffline(false)
  p.sequence++
  await request.post('/api/v1/telemetry', { data: p })
  await expect(page.locator('.connection')).toContainText('연결됨')
})
test('demo timeout, late results, reset and mid-request disconnect', async ({ page }) => {
  await page.goto('/demo')
  await page.getByLabel('응답 제한 시간(초)', { exact: true }).fill('0.2')
  await page.getByLabel('원격 정지 결과', { exact: true }).selectOption('late')
  await page.getByRole('button', { name: '원격 정지', exact: true }).click()
  await expect(page.getByRole('button', { name: '순찰 재개', exact: true })).toBeDisabled()
  await expect(page.locator('.result')).toContainText('정지 여부 확인 불가')
  await page.waitForTimeout(2000)
  await expect(page.locator('.result')).not.toContainText('정지 상태 확인됨')
  await expect(page.locator('.alert-row')).toHaveCount(1)
  await page.getByRole('button', { name: '시나리오 초기화' }).click()
  await expect(page.locator('.result')).toHaveCount(0)
  await page.getByRole('button', { name: '원격 정지', exact: true }).click()
  await page.getByRole('button', { name: '진행 중 연결 끊기' }).click()
  await expect(page.locator('.result')).toContainText('정지 여부 확인 불가')
  await page.getByLabel('화면 상태', { exact: true }).selectOption('normal')
  await page.waitForTimeout(1000)
  await expect(page.locator('.result')).toHaveCount(0)
  await expect(page.locator('.alert-row')).toHaveCount(0)
})
test('restart modal keyboard focus trap, Escape and return; resume reasons', async ({ page }) => {
  await page.goto('/demo')
  const restart = page.getByRole('button', { name: '프로그램 재시작', exact: true })
  await restart.click()
  await expect(page.getByRole('button', { name: '취소', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('button', { name: '재시작', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: '취소', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(restart).toBeFocused()
  for (const state of ['patrolling', 'empty', 'unknown']) {
    await page.getByLabel('가상 순찰 상태').selectOption(state)
    await expect(page.getByRole('button', { name: '순찰 재개', exact: true })).toBeDisabled()
  }
})
for (const width of [1440, 1024, 768, 390]) {
  test(`layout at ${width}px and all scenarios`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1100 })
    await page.goto('/demo')
    for (const scenario of ['normal', 'partial', 'delayed', 'disconnected', 'initial', 'server']) {
      await page.getByLabel('화면 상태', { exact: true }).selectOption(scenario)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      if (scenario === 'initial') await expect(page.locator('.speed strong')).toHaveText('—')
      if (scenario === 'server') await expect(page.locator('tbody')).not.toContainText('수신 중')
    }
    await page.getByLabel('화면 상태', { exact: true }).selectOption('normal')
    mkdirSync('../artifacts', { recursive: true })
    await page.screenshot({ path: `../artifacts/demo-${width}.png`, fullPage: true })
    await page.goto('/')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../artifacts/live-${width}.png`, fullPage: true })
  })
}

for (const command of ['stop', 'resume', 'restart'] as Command[]) {
  for (const outcome of ['success', 'reject', 'no_response', 'no_confirmation'] as Outcome[]) {
    test(`command ${command} outcome ${outcome}`, async ({ page }) => {
      await page.goto('/demo')
      await page.getByLabel('응답 제한 시간(초)', { exact: true }).fill('1')
      await page.getByLabel('상태 확인 제한 시간(초)', { exact: true }).fill('1.5')
      await page.getByLabel(`${commandNames[command]} 결과`, { exact: true }).selectOption(outcome)
      await page.getByRole('button', { name: commandNames[command], exact: true }).click()
      if (command === 'restart') await page.getByRole('button', { name: '재시작', exact: true }).click()
      const result = outcome === 'success' ? 'success' : outcome === 'reject' ? 'failed' : 'unknown'
      await expect(page.locator('.result')).toContainText(resultLabels[command][result])
      await expect(page.locator('.result .steps')).toContainText('요청 전송')
      await expect(page.locator('.alert-row')).toHaveCount(1)
    })
  }
}

test('silent stream becomes a browser problem and tab return fetches a fresh snapshot', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetry() })
  const state = await (await request.get('/api/v1/state')).json()
  await page.routeWebSocket('**/api/v1/stream', ws => { ws.send(JSON.stringify(state)) })
  await page.goto('/')
  await expect(page.locator('.connection')).toContainText('연결됨')
  await expect(page.getByRole('alert')).toContainText('서버 상태를 갱신할 수 없습니다', { timeout: 5000 })
  await request.post('/api/v1/telemetry', { data: telemetry() })
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await expect(page.locator('.connection')).toContainText('연결됨')
})
