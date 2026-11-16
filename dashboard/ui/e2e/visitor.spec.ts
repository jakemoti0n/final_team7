import { test, expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { mkdirSync } from 'node:fs'
// 방문자 안내(/visitor): 로그인 없이 읽기 전용. 8017 서버는 config.json에서 visitor_enabled: true, 8018(로그인 켬)은 꺼짐

function patrolling(x: number, y: number) {
  const at = new Date().toISOString()
  return { schema_version: 3, robot_id: 'LIMBO-01', bridge_session_id: randomUUID(), sequence: 1, sent_at: at, source_clock: 'ros_sim',
    topics: Object.fromEntries(['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'].map(key => [key, { header_stamp: { sec: 0, nanosec: 0 }, last_received_at: at, age_ms: 0, received_count: 1, receive_hz: 10 }])),
    motion: { linear_speed_mps: .2, angular_velocity_radps: 0, last_received_at: at, age_ms: 0 },
    patrol: { state: 'patrolling', waypoint_index: 0, waypoint_count: 2, waypoint_name: 'A', has_resumable_task: false, reason: 'navigating', update_count: 1, last_received_at: at, age_ms: 0 },
    pose: { frame_id: 'map', x, y, yaw: 0, position_std_m: .1, last_received_at: at, age_ms: 0 },
    launcher: { commands: ['pause', 'resume', 'start', 'stop'], state: 'running', pid: 123, exit_code: null, waypoints_revision: 'c'.repeat(64), log: '/tmp/limbo-patrol-e2e.log', other_patrol_running: false } }
}

const robot = (page: Page) => page.getByTestId('visitor-robot').filter({ hasText: 'LIMBO-01' })
const marker = (page: Page) => page.locator('[data-testid=visitor-marker][data-robot="LIMBO-01"]')

test('visitor demo on a phone and a tablet', async ({ page }) => {
  mkdirSync('../artifacts', { recursive: true })
  for (const width of [390, 1024]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 })
    await page.goto('/visitor?demo')
    await expect(page.getByRole('heading', { name: 'LIMBO 실시간 안내' })).toBeVisible()
    await expect(page).toHaveTitle('LIMBO 실시간 안내')
    await expect(page.getByTestId('visitor-count')).toHaveText('LIMBO 2대 운행 중')
    const robots = page.getByTestId('visitor-robot')
    await expect(robots).toHaveCount(3)
    await expect(robots.nth(0)).toContainText('순찰 중')
    await expect(robots.nth(1)).toContainText('대기 중')
    await expect(robots.nth(2)).toContainText('연결 끊김')
    await expect(robots.nth(2)).toContainText('마지막 위치')
    await expect(page.getByTestId('visitor-marker')).toHaveCount(3)
    await expect(page.locator('.visitor-marker.stale')).toHaveCount(1)
    // 운영자 화면의 사이드바·제어는 없다
    await expect(page.locator('.sidebar')).toHaveCount(0)
    await expect(page.getByRole('button')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../artifacts/visitor-demo-${width}.png`, fullPage: true })
  }
})

test('visitor page shows a live robot without login and marks lost updates', async ({ page, request }) => {
  // Bridge처럼 1초마다 보낸다 (한 번만 보내면 3초 뒤 수신 지연이 된다)
  const send = async () => expect((await request.post('/api/v1/telemetry', { data: patrolling(1.2, -0.8) })).ok()).toBe(true)
  await send()
  const bridge = setInterval(() => { void send().catch(() => {}) }, 1000)
  try {
    const body = await (await request.get('/api/v1/visitor/state')).json()
    expect(body.robots.find((r: { robot_id: string }) => r.robot_id === 'LIMBO-01')).toEqual(
      { robot_id: 'LIMBO-01', status: 'patrolling', position: { x: 1, y: -1, stale: false, age_s: 0 } })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/visitor')
    await expect(robot(page)).toContainText('순찰 중')
    await expect(marker(page)).toHaveCount(1)
    await expect(marker(page)).not.toHaveClass(/stale/)
    await expect(page.locator('.visitor-map image')).toHaveAttribute('href', '/api/v1/visitor/map.png')
    // 서버에서 받지 못하게 되면 지난 정보로 표시하고 지금 대수를 모른다고 말한다
    await page.route('**/api/v1/visitor/state', route => route.abort())
    await expect(page.getByTestId('visitor-problem')).toBeVisible({ timeout: 8000 })
    await expect(page.getByTestId('visitor-count')).toHaveText('지금 운행 대수를 확인할 수 없습니다')
    await expect(robot(page)).toContainText('확인 불가')
    await expect(robot(page)).toContainText('마지막 위치')
    await expect(page.locator('.visitor-marker:not(.stale)')).toHaveCount(0)
  } finally {
    clearInterval(bridge)
  }
  // 서버가 방문자 화면을 끄면(404) 안내를 멈춘다
  await page.unroute('**/api/v1/visitor/state')
  await page.route('**/api/v1/visitor/state', route => route.fulfill({ status: 404, json: { error: { code: 'visitor_disabled', message: '' } } }))
  await expect(page.getByTestId('visitor-closed')).toBeVisible({ timeout: 8000 })
})

test('visitor page is off unless enabled', async ({ request }) => {
  for (const path of ['/visitor', '/api/v1/visitor/state', '/api/v1/visitor/map.png'])
    expect((await request.get(`http://127.0.0.1:8018${path}`)).status(), path).toBe(404)
  expect((await request.get('http://127.0.0.1:8018/visitor?demo')).status()).toBe(200)
})
