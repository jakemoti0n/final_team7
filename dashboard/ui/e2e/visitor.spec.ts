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
    // 데모에는 안내 약도가 있다: 처음엔 「안내 지도」 탭, 「LiDAR 지도」 탭에도 같은 위치
    const main = page.getByTestId('visitor-guide-map'), lidar = page.getByTestId('visitor-lidar')
    const guideTab = page.getByRole('tab', { name: '안내 지도' }), lidarTab = page.getByRole('tab', { name: 'LiDAR 지도' })
    await expect(guideTab).toHaveAttribute('aria-selected', 'true')
    await expect(main).toBeVisible()
    await expect(lidar).toBeHidden()
    await expect(main.getByTestId('guide-area')).toHaveCount(4)
    await expect(main).toHaveAttribute('aria-label', /행사장 안내 약도 \(행사장, 201 강의실, 화장실, 복도\)/)
    await expect(main.getByTestId('visitor-marker')).toHaveCount(3)
    await expect(main.locator('.visitor-marker.stale')).toHaveCount(1)
    await expect(lidar.getByTestId('visitor-marker')).toHaveCount(3)
    // 운영자 화면의 사이드바·제어는 없다 (누르는 것은 지도 탭 둘뿐)
    await expect(page.locator('.sidebar')).toHaveCount(0)
    await expect(page.getByRole('button')).toHaveCount(0)
    await expect(page.getByRole('tab')).toHaveCount(2)
    await lidarTab.click()
    await expect(lidarTab).toHaveAttribute('aria-selected', 'true')
    await expect(lidar).toBeVisible()
    await expect(main).toBeHidden()
    await expect(lidar.locator('svg')).toBeVisible()
    await expect(lidar.locator('[data-robot="LIMBO-01"]')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: `../artifacts/visitor-demo-lidar-${width}.png`, fullPage: true })
    // 키보드: 왼쪽 화살표로 안내 지도로 돌아간다
    await lidarTab.press('ArrowLeft')
    await expect(guideTab).toBeFocused()
    await expect(guideTab).toHaveAttribute('aria-selected', 'true')
    await expect(main).toBeVisible()
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
    // 시험 서버에는 약도가 없어 구역 이름은 없다. 진행은 번호만(지점 이름은 나가지 않음)
    expect(body.robots.find((r: { robot_id: string }) => r.robot_id === 'LIMBO-01')).toEqual(
      { robot_id: 'LIMBO-01', status: 'patrolling', position: { x: 1, y: -1, stale: false, age_s: 0 },
        area: null, next_area: null, progress: { done: 0, total: 2 }, moving: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/visitor')
    await expect(robot(page)).toContainText('순찰 중')
    await expect(marker(page)).toHaveCount(1)
    await expect(marker(page)).not.toHaveClass(/stale/)
    // 안내 약도가 없으면(시험 서버는 아직 저장 전) 자동 약도가 메인
    await expect(page.getByTestId('visitor-guide-map')).toHaveCount(0)
    await expect(page.getByTestId('visitor-map-background')).toHaveAttribute('href', '/api/v1/visitor/map_sketch.svg')
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

test('visitor page shows the guide drawn on the control screen, with the real map in a tab', async ({ page, request }) => {
  // 시험 서버의 약도 파일은 만들지 않는다: 약도 API를 가로채 그린 약도를 준다
  const guide = {
    revision: 'g1', bounds: { x_min: -10, y_min: -10, x_max: 10, y_max: 10 },
    categories: [{ key: 'event', label: '행사장', color: '#FCE9C8', icon: 'event' }],
    areas: [{ name: '본 행사장', category: 'event', polygon: [[-2, -3], [4, -3], [4, 2], [-2, 2]] }],
    markers: [{ name: '정문', category: 'event', x: -1, y: -2.5 }], image: null,
  }
  let guideRequests = 0
  await page.route('**/api/v1/visitor/state', async route => {
    const body = await (await route.fetch()).json()
    await route.fulfill({ json: { ...body, guide: 'g1' } })
  })
  await page.route('**/api/v1/visitor/guide', route => { guideRequests++; return route.fulfill({ json: guide }) })
  const send = async (x: number, y: number) => expect((await request.post('/api/v1/telemetry', { data: patrolling(x, y) })).ok()).toBe(true)
  await send(1.2, -0.8)
  const bridge = setInterval(() => { void send(1.2, -0.8).catch(() => {}) }, 1000)
  try {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/visitor')
    const main = page.getByTestId('visitor-guide-map')
    await expect(main.locator('[data-testid=guide-area][data-name="본 행사장"]')).toBeVisible()
    await expect(main.locator('[data-testid=visitor-marker][data-robot="LIMBO-01"]')).toHaveCount(1)
    // 위치는 약도의 m 좌표 그대로: (1, -1) → SVG (1, 1)
    await expect(main.locator('[data-testid=visitor-marker][data-robot="LIMBO-01"]')).toHaveAttribute('transform', 'translate(1 1)')
    await expect(page.getByTestId('visitor-lidar').locator('[data-robot="LIMBO-01"]')).toHaveCount(1)
    await page.waitForTimeout(3500)                                     // 다음 상태를 받아도 판이 같으면 다시 받지 않는다
    expect(guideRequests).toBe(1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: '../artifacts/visitor-guide-390.png', fullPage: true })
  } finally { clearInterval(bridge) }
})
