import { test, expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { mkdirSync } from 'node:fs'
// 로봇 하단 디스플레이(/display): 로그인 없이 읽기만, 1920×1080 한 장. 8017 서버는 visitor_enabled: true,
// display_dir은 저장소의 dashboard/guides/display (시험은 이 파일을 바꾸지 않고, 필요하면 응답을 가로챈다)

function telemetry(patrol: boolean) {
  const at = new Date().toISOString()
  return { schema_version: 3, robot_id: 'LIMBO-01', bridge_session_id: randomUUID(), sequence: 1, sent_at: at, source_clock: 'ros_sim',
    topics: Object.fromEntries(['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'].map(key => [key, { header_stamp: { sec: 0, nanosec: 0 }, last_received_at: at, age_ms: 0, received_count: 1, receive_hz: 10 }])),
    motion: { linear_speed_mps: .2, angular_velocity_radps: 0, last_received_at: at, age_ms: 0 },
    patrol: patrol ? { state: 'patrolling', waypoint_index: 1, waypoint_count: 2, waypoint_name: 'B', has_resumable_task: false, reason: 'navigating', update_count: 1, last_received_at: at, age_ms: 0 }
      : { state: null, waypoint_index: null, waypoint_count: null, waypoint_name: null, has_resumable_task: null, reason: null, update_count: 0, last_received_at: null, age_ms: null },
    pose: { frame_id: 'map', x: 1.2, y: -0.8, yaw: 0, position_std_m: .1, last_received_at: at, age_ms: 0 },
    launcher: patrol ? { commands: ['pause', 'resume', 'start', 'stop'], state: 'running', pid: 123, exit_code: null, waypoints_revision: 'c'.repeat(64), log: '/tmp/limbo-patrol-e2e.log', other_patrol_running: false }
      : { commands: ['pause', 'resume', 'start', 'stop'], state: 'idle', pid: null, exit_code: null, waypoints_revision: null, log: null, other_patrol_running: false } }
}

const screen = (page: Page) => page.getByTestId('display-screen')

/** 화면에 보이는 글자 중 가장 작은 글자 크기(px, 1920×1080 기준). DEMO 표시·소리 안내(운영자용)는 뺀다 */
const smallestText = (page: Page) => page.evaluate(() => {
  const root = document.querySelector('[data-testid=display-screen]')!
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let smallest = Infinity
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement!
    if (!node.textContent!.trim() || el.closest('.display-demo, .display-sound-hint, .display-mark')) continue
    const box = el.getBoundingClientRect()
    if (box.width === 0 || box.height === 0) continue
    smallest = Math.min(smallest, parseFloat(getComputedStyle(el).fontSize))
  }
  return smallest
})
const SLIDE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="#fde68a"/></svg>'

/** 짧은 장면 길이와 팜플렛 1장으로 내용 응답을 바꿔 준다 (저장소 파일은 그대로) */
async function shortContent(page: Page) {
  await page.route('**/api/v1/display/content', route => route.fulfill({ json: {
    revision: 'e2e', message: '시험 문구', schedule: [],
    slides: [{ file: 'e2e.svg', width: 1920, height: 1080, type: 'image/svg+xml', url: '/api/v1/display/slides/e2e.svg?v=1' }],
    eco: { enabled: false },   // 이 시험은 ① ↔ ②만 (나무는 따로)
    timing: { location_s: 2, slides_s: 2, count_s: 10, trash_alert_s: 10, passing_s: 8, passing_cooldown_s: 60 } } }))
  await page.route('**/api/v1/display/slides/**', route => route.fulfill({ contentType: 'image/svg+xml', body: SLIDE_SVG }))
}

test('display demo: robot place, schedule, QR, then the pamphlet with a small QR', async ({ page }) => {
  test.setTimeout(60000)
  mkdirSync('../artifacts', { recursive: true })
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/display?demo')
  await expect(page).toHaveTitle('LIMBO 실시간 안내')
  await expect(screen(page)).toHaveAttribute('data-scene', 'location')
  await expect(page.getByTestId('display-demo')).toBeVisible()                       // 가상 데이터 표시
  await expect(page.getByTestId('display-hud-status')).toHaveText('LIMBO-01 순찰 중')
  await expect(page.getByTestId('display-clock')).toHaveText(/^\d{2}:\d{2}$/)
  await expect(page.getByTestId('display-title')).toHaveText(/에 있어요$/)
  await expect(page.getByTestId('display-badge')).toHaveText('순찰 중')
  await expect(page.getByTestId('display-progress')).toHaveText(/\d \/ 4 지점/)
  const qr = page.getByTestId('display-qr')
  await expect(qr).toHaveAttribute('data-value', 'http://127.0.0.1:8017/visitor')
  expect((await qr.boundingBox())!.width).toBeGreaterThanOrEqual(430)               // 1920 폭에서 440 px (멀리서도)
  await expect(page.getByTestId('display-event')).toHaveCount(3)
  await expect(page.locator('[data-testid=display-event][data-state=now]')).toContainText('LIMBO 데모')
  await expect(page.getByTestId('display-message')).toHaveText('쓰레기는 LIMBO에게 주세요.')
  await expect(page.getByTestId('display-dots').locator('i')).toHaveCount(4)       // ① ② ① ⑤
  // 13.3인치 하단 화면에서 읽히게 본문은 40 px 이상 (PRD v0.3.6). DEMO 표시는 운영 화면에 없으므로 뺀다
  expect(await smallestText(page)).toBeGreaterThanOrEqual(40)
  // 조작 없는 화면: 단추·링크·사이드바가 없다
  await expect(page.getByRole('button')).toHaveCount(0)
  await expect(page.getByRole('link')).toHaveCount(0)
  // 데모 로봇은 3 s에 출발해 「지나갑니다」가 5 s 뜬다. 그동안 회전은 멈췄다가 이어 간다
  await expect(page.getByTestId('display-passing')).toBeVisible({ timeout: 8000 })
  await expect(page.getByTestId('display-passing')).toHaveCount(0, { timeout: 8000 })
  // 멈추지 않았다면 출발 뒤 12 s(오버레이가 내려가고 약 4 s)에 ②로 넘어갔을 것: 6 s 뒤에도 ①이어야 한다
  await page.waitForTimeout(6000)
  await expect(screen(page)).toHaveAttribute('data-scene', 'location')
  await page.waitForTimeout(800)                                                     // 0.6 s 페이드가 끝난 뒤 찍는다
  await page.screenshot({ path: '../artifacts/display-demo-location.png' })
  // 데모는 ① 12 s(+ 오버레이로 멈춘 5 s) 뒤 ② 팜플렛 (작은 QR은 오른쪽 아래)
  await expect(screen(page)).toHaveAttribute('data-scene', 'slides', { timeout: 16000 })
  await expect(page.getByRole('img', { name: '행사장 팜플렛 1/2' })).toBeVisible()
  const mini = page.locator('.display-mini-qr')
  const box = (await mini.boundingBox())!
  expect(box.x + box.width).toBeGreaterThan(1800)
  expect(box.y + box.height).toBeGreaterThan(950)
  // 작은 QR 300 px, 상자는 팜플렛이 비워 두는 오른쪽 아래 400 × 460 px 안에 (PRD v0.3.6)
  expect((await mini.getByTestId('display-qr').boundingBox())!.width).toBeGreaterThanOrEqual(295)
  expect(box.x).toBeGreaterThanOrEqual(1920 - 400)
  expect(box.y).toBeGreaterThanOrEqual(1080 - 460)
  await expect(page.getByTestId('display-hud')).toBeVisible()                        // HUD는 팜플렛 위에도
  await page.waitForTimeout(800)                                                     // 0.6 s 페이드가 끝난 뒤 찍는다
  await page.screenshot({ path: '../artifacts/display-demo-slides.png' })
})

test('display keeps 16:9 and fits smaller or odd-shaped screens without scrolling', async ({ page }) => {
  for (const [width, height] of [[1280, 720], [1024, 768], [1920, 1200]]) {
    await page.setViewportSize({ width, height })
    await page.goto('/display?demo')
    const box = (await screen(page).boundingBox())!
    expect(Math.abs(box.width / box.height - 16 / 9)).toBeLessThan(.01)
    expect(box.x).toBeGreaterThanOrEqual(-1)
    expect(box.y).toBeGreaterThanOrEqual(-1)
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1)
    expect(box.y + box.height).toBeLessThanOrEqual(height + 1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight)).toBe(true)
  }
})

test('display shows the live robot from the server and survives losing the server', async ({ page, request }) => {
  const send = async () => expect((await request.post('/api/v1/telemetry', { data: telemetry(true) })).ok()).toBe(true)
  await send()
  const bridge = setInterval(() => { void send().catch(() => {}) }, 1000)
  try {
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/display')
    await expect(page.getByTestId('display-hud-status')).toHaveText('LIMBO-01 순찰 중')
    // 시험 서버에는 약도가 없다: 구역을 지어내지 않고 일반 문구
    await expect(page.getByTestId('display-title')).toHaveText('행사장을 돌고 있어요')
    await expect(page.getByTestId('display-detail')).toHaveText('순찰 경로를 따라 가는 중')
    await expect(page.getByTestId('display-progress')).toHaveText(/1 \/ 2 지점/)
    // 저장소의 기본 내용(display.json)을 서버에서 받았다
    await expect(page.getByTestId('display-message')).toHaveText('쓰레기는 LIMBO에게 주세요.')
    // 서버에서 받지 못하게 되면: HUD 「연결 끊김」, 위치는 확인할 수 없다고, 시계는 계속
    await page.route('**/api/v1/visitor/state', route => route.abort())
    await expect(page.getByTestId('display-hud-status')).toHaveText('연결 끊김', { timeout: 8000 })
    await expect(page.getByTestId('display-title')).toHaveText('지금 위치를 확인할 수 없어요')
    await expect(page.getByTestId('display-progress')).toHaveCount(0)
    await expect(page.getByTestId('display-clock')).toBeVisible()
  } finally {
    clearInterval(bridge)
  }
  // 서버가 방문자 안내를 끄면(404) 안내를 멈춘다
  await page.unroute('**/api/v1/visitor/state')
  await page.route('**/api/v1/visitor/state', route => route.fulfill({ status: 404, json: { error: { code: 'visitor_disabled', message: '' } } }))
  await expect(page.getByTestId('display-closed')).toBeVisible({ timeout: 8000 })
  await expect(page.getByTestId('display-dots')).toHaveCount(0)
})

test('display rotates ① → ② → ① and stays on ① while the robot is idle', async ({ page, request }) => {
  await shortContent(page)
  const send = async (patrol: boolean) => expect((await request.post('/api/v1/telemetry', { data: telemetry(patrol) })).ok()).toBe(true)
  await send(true)
  let patrol = true
  const bridge = setInterval(() => { void send(patrol).catch(() => {}) }, 1000)
  try {
    await page.setViewportSize({ width: 1280, height: 720 })
    await page.goto('/display')
    await expect(page.getByTestId('display-events-empty')).toHaveText('예정된 행사가 없습니다.')
    await expect(screen(page)).toHaveAttribute('data-scene', 'slides', { timeout: 6000 })
    await expect(page.getByTestId('display-slide')).toHaveAttribute('data-file', 'e2e.svg')
    await expect(screen(page)).toHaveAttribute('data-scene', 'location', { timeout: 6000 })
    // 대기 중(순찰 안 함)이면 ①에 머문다 (PRD v0.3 R)
    patrol = false
    await send(false)
    await expect(page.getByTestId('display-hud-status')).toHaveText('LIMBO-01 대기 중', { timeout: 6000 })
    for (let i = 0; i < 5; i++) {
      await expect(screen(page)).toHaveAttribute('data-scene', 'location')
      await page.waitForTimeout(1000)
    }
    await expect(page.getByTestId('display-dots')).toBeVisible()
  } finally {
    clearInterval(bridge)
  }
})

test('display is off unless the visitor guide is enabled', async ({ request }) => {
  for (const path of ['/display', '/api/v1/display/content'])
    expect((await request.get(`http://127.0.0.1:8018${path}`)).status(), path).toBe(404)
  expect((await request.get('http://127.0.0.1:8018/display?demo')).status()).toBe(200)
})

// ---- 장면 ④ 「LIMBO가 지나갑니다」 ----

const WAV = Buffer.concat([Buffer.from('RIFF'), Buffer.from([36, 0, 0, 0]), Buffer.from('WAVEfmt '), Buffer.alloc(28)])

/** 로봇 상태를 시험이 정한다: moving만 바꿔 가며 출발을 흉내 낸다 */
async function fakeRobot(page: Page) {
  const robot = { moving: false }
  await page.route('**/api/v1/visitor/state', route => route.fulfill({ json: {
    server_utc: new Date().toISOString(), operating: 1, map: null, guide: null, display: 'e2e-sound',
    robots: [{ robot_id: 'LIMBO-01', status: 'patrolling', position: { x: 1, y: 1, stale: false, age_s: 0 },
      area: '복도', next_area: '201 강의실', progress: { done: 3, total: 10 }, moving: robot.moving }] } }))
  await page.route('**/api/v1/display/content', route => route.fulfill({ json: {
    revision: 'e2e-sound', message: null, schedule: [], slides: [],
    sound: { file: 'passing.wav', type: 'audio/wav', url: '/api/v1/display/sound/passing.wav?v=1' },
    timing: { location_s: 40, slides_s: 30, count_s: 10, trash_alert_s: 10, passing_s: 4, passing_cooldown_s: 30 } } }))
  await page.route('**/api/v1/display/sound/**', route => route.fulfill({ contentType: 'audio/wav', body: WAV }))
  return robot
}

/** 재생 요청을 기록하고, 화면을 누르기 전에는 브라우저처럼 소리를 막는다 */
async function recordPlays(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { plays: string[]; touched: boolean }
    w.plays = []
    w.touched = false
    addEventListener('pointerdown', () => { w.touched = true }, true)
    HTMLMediaElement.prototype.play = function () {
      if (!w.touched) return Promise.reject(new DOMException('blocked', 'NotAllowedError'))
      if (!this.src.startsWith('data:')) w.plays.push(new URL(this.src).pathname)
      return Promise.resolve()
    }
  })
}
const plays = (page: Page) => page.evaluate(() => (window as unknown as { plays: string[] }).plays)

test('passing: overlay and one sound when the robot sets off, then a cooldown', async ({ page }) => {
  await recordPlays(page)
  const robot = await fakeRobot(page)
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/display')
  await expect(page.getByTestId('display-title')).toHaveText('복도에 있어요')
  // 소리가 막혀 있으면 안내, 한 번 누르면 풀린다
  await expect(page.getByTestId('display-sound-hint')).toHaveText('화면을 한 번 누르면 안내 소리가 켜져요')
  await page.mouse.click(960, 540)
  await expect(page.getByTestId('display-sound-hint')).toHaveCount(0)
  await expect(page.getByTestId('display-passing')).toHaveCount(0)                      // 멈춰 있으면 없음
  robot.moving = true                                                                    // 출발
  await expect(page.getByTestId('display-passing')).toBeVisible({ timeout: 6000 })
  await expect(page.getByTestId('display-passing')).toContainText('LIMBO가 지나갑니다')
  await expect(page.getByTestId('display-passing-detail')).toHaveText('복도 → 201 강의실 쪽으로 · 길을 조금 비켜 주세요')
  await expect(page.getByTestId('display-hud')).toBeVisible()                           // HUD는 그대로
  await expect.poll(() => plays(page)).toEqual(['/api/v1/display/sound/passing.wav'])
  await page.waitForTimeout(800)
  await page.screenshot({ path: '../artifacts/display-passing.png' })
  await expect(page.getByTestId('display-passing')).toHaveCount(0, { timeout: 6000 })   // 4 s 뒤 내림
  // 쿨다운(30 s) 안에 다시 멈췄다 출발해도 띄우지 않는다
  robot.moving = false
  await page.waitForTimeout(3500)
  robot.moving = true
  await page.waitForTimeout(4000)
  await expect(page.getByTestId('display-passing')).toHaveCount(0)
  expect(await plays(page)).toHaveLength(1)
})

test('passing in the demo: the demo robot stops at corners and sets off again', async ({ page }) => {
  await recordPlays(page)
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.goto('/display?demo')
  await page.mouse.click(10, 10)                                                         // 소리 막힘 풀기
  await expect(page.getByTestId('display-passing')).toBeVisible({ timeout: 8000 })
  await expect(page.getByTestId('display-passing-detail')).toContainText('길을 조금 비켜 주세요')
  // 데모도 서버의 소리 파일(display.json의 passing.mp3)을 튼다 (브라우저 음성 아님)
  await expect.poll(() => plays(page)).toEqual(['/api/v1/display/sound/passing.mp3'])
  await expect(page.getByTestId('display-passing')).toHaveCount(0, { timeout: 8000 })
})

test('passing in the demo without a sound file on the server: falls back to no file', async ({ page }) => {
  await recordPlays(page)
  await page.route('**/api/v1/display/content', route => route.fulfill({ status: 404, json: { detail: 'display_not_configured' } }))
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.goto('/display?demo')
  await page.mouse.click(10, 10)
  await expect(page.getByTestId('display-passing')).toBeVisible({ timeout: 8000 })
  expect(await plays(page)).toEqual([])                                                  // 파일 없음 → 브라우저 음성(있으면) 또는 소리 없이
})

const ECO = { schema_version: 1, observed_at: '', window_start: '', window_end: '', source: 'e2e', evaluation_method: 'ai_bin_inspection',
  verified_correct_count: 18, verified_total_count: 20, quality: 'ok' }
function ecoBody(correct: number, total = 20) {
  const now = new Date(), start = new Date(now.getTime() - 3600_000)
  return { ...ECO, observed_at: now.toISOString(), window_start: start.toISOString(), window_end: now.toISOString(),
    verified_correct_count: correct, verified_total_count: total }
}

test('eco tree in the demo: initial first, with the small QR in the same corner', async ({ page }) => {
  test.setTimeout(60000)
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/display?demo')
  // 데모: ① 12 s(+ 지나갑니다 5 s) → ② 8 s → ① 12 s → ⑤ 나무. 첫 바퀴는 초기 나무
  await expect(screen(page)).toHaveAttribute('data-scene', 'eco', { timeout: 45000 })
  const eco = page.getByTestId('display-eco')
  await expect(eco).toHaveAttribute('data-tree', 'initial')
  await expect(page.getByTestId('display-eco-title')).toHaveText('분리수거 결과를 모으는 중이에요')
  await expect(page.getByTestId('display-eco-detail')).toHaveCount(0)               // 판정 전에는 숫자 없음
  await expect(eco.locator('img.display-eco-tree')).toHaveJSProperty('complete', true)
  expect(await eco.locator('img.display-eco-tree').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(900)
  const box = (await page.getByTestId('display-mini-qr').boundingBox())!
  expect(box.x + box.width).toBeGreaterThan(1800)
  expect(box.y + box.height).toBeGreaterThan(950)
  expect(await smallestText(page)).toBeGreaterThanOrEqual(40)
  await page.waitForTimeout(800)
  await page.screenshot({ path: '../artifacts/display-demo-eco-initial.png' })
})

test('eco tree from the server: positive, negative, and initial again when the server is lost', async ({ page, request }) => {
  await page.route('**/api/v1/display/content', route => route.fulfill({ json: {
    revision: 'e2e-eco', message: null, schedule: [], slides: [], eco: { enabled: true },
    timing: { location_s: 1, slides_s: 2, eco_s: 60, count_s: 10, trash_alert_s: 10, passing_s: 8, passing_cooldown_s: 60 } } }))
  const send = async () => expect((await request.post('/api/v1/telemetry', { data: telemetry(true) })).ok()).toBe(true)
  await send()
  const bridge = setInterval(() => { void send().catch(() => {}) }, 1000)
  try {
    // 시험 서버(allow_no_robot_token)는 토큰 없이 받는다. 형식이 틀리면 422, 정상은 판정을 돌려준다
    expect((await request.post('/api/v1/eco', { data: { ...ecoBody(18), extra: 1 } })).status()).toBe(422)
    const accepted = await request.post('/api/v1/eco', { data: ecoBody(18) })
    expect(accepted.ok()).toBe(true)
    expect((await accepted.json()).eco).toEqual({ state: 'positive', rate_percent: 90, correct: 18, total: 20, method: 'ai_bin_inspection' })
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/display')
    await expect(screen(page)).toHaveAttribute('data-scene', 'eco', { timeout: 6000 })
    await expect(page.getByTestId('display-eco')).toHaveAttribute('data-tree', 'positive')
    await expect(page.getByTestId('display-eco-title')).toHaveText('분리수거를 잘하고 있어요!')
    await expect(page.getByTestId('display-eco-detail')).toHaveText('수거함을 비운 뒤 · AI 확인 20건 중 18건 바르게')
    await expect(page.getByTestId('display-eco-hint')).toHaveCount(0)
    await page.waitForTimeout(800)
    await page.screenshot({ path: '../artifacts/display-eco-positive.png' })
    // 성공률이 떨어지면 (장면은 그대로, 다음 상태를 받을 때) 부정 나무와 부드러운 문구
    expect((await request.post('/api/v1/eco', { data: ecoBody(13) })).ok()).toBe(true)
    await expect(page.getByTestId('display-eco')).toHaveAttribute('data-tree', 'negative', { timeout: 6000 })
    await expect(page.getByTestId('display-eco-title')).toHaveText('분리수거가 잘 안 되고 있어요')
    await expect(page.getByTestId('display-eco-detail')).toHaveText('수거함을 비운 뒤 · AI 확인 20건 중 13건 바르게')
    await expect(page.getByTestId('display-eco-hint')).toHaveText('재활용할 수 있는 것은 재활용 칸, 나머지는 일반 칸에 넣어 주세요')
    expect(await smallestText(page)).toBeGreaterThanOrEqual(40)
    // 두 줄이 되는 긴 문구도 1920 폭 안에 (넘치면 HUD 시계·작은 QR이 잘린다)
    for (const id of ['display-eco-title', 'display-eco-hint', 'display-mini-qr', 'display-clock']) {
      const box = (await page.getByTestId(id).boundingBox())!
      expect(box.x + box.width, id).toBeLessThanOrEqual(1920)
    }
    await page.waitForTimeout(800)
    await page.screenshot({ path: '../artifacts/display-eco-negative.png' })
    // 서버에서 받지 못하면 판정이 오래됐으므로 숫자 없이 초기 나무
    await page.route('**/api/v1/visitor/state', route => route.abort())
    await expect(page.getByTestId('display-eco')).toHaveAttribute('data-tree', 'initial', { timeout: 8000 })
    await expect(page.getByTestId('display-eco-detail')).toHaveCount(0)
  } finally {
    clearInterval(bridge)
    // 다른 시험이 이 판정을 보지 않게 표본 부족(초기 나무)으로 되돌린다
    await request.post('/api/v1/eco', { data: ecoBody(0, 0) })
  }
})

test('eco words from display.json: longest words fit, missing ones fall back, hint can be removed', async ({ page, request }) => {
  // 서버가 허락하는 가장 긴 문구 (server/display.py ECO_TEXT_LIMITS: 제목·위 줄 24자, 안내 60자)
  const words = { kicker: '가'.repeat(24), negative: '나'.repeat(24), negative_hint: '다'.repeat(60) }
  let text: Record<string, string | null> = words
  await page.route('**/api/v1/display/content', route => route.fulfill({ json: {
    revision: 'e2e-eco-words', message: null, schedule: [], slides: [], eco: { enabled: true, text },
    timing: { location_s: 1, slides_s: 2, eco_s: 60, count_s: 10, trash_alert_s: 10, passing_s: 8, passing_cooldown_s: 60 } } }))
  const send = async () => expect((await request.post('/api/v1/telemetry', { data: telemetry(true) })).ok()).toBe(true)
  await send()
  const bridge = setInterval(() => { void send().catch(() => {}) }, 1000)
  try {
    expect((await request.post('/api/v1/eco', { data: ecoBody(13) })).ok()).toBe(true)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await page.goto('/display')
    await expect(screen(page)).toHaveAttribute('data-scene', 'eco', { timeout: 6000 })
    await expect(page.getByTestId('display-eco')).toHaveAttribute('data-tree', 'negative')
    await expect(page.getByTestId('display-eco-kicker')).toHaveText(words.kicker)
    await expect(page.getByTestId('display-eco-title')).toHaveText(words.negative)
    await expect(page.getByTestId('display-eco-detail')).toHaveText('수거함을 비운 뒤 · AI 확인 20건 중 13건 바르게')   // 숫자 줄은 그대로
    await expect(page.getByTestId('display-eco-hint')).toHaveText(words.negative_hint)
    // 가장 긴 문구도 1920 폭 안, 글 칸 아래 끝이 작은 QR 위에서 끝난다
    const qr = (await page.getByTestId('display-mini-qr').boundingBox())!
    for (const id of ['display-eco-kicker', 'display-eco-title', 'display-eco-hint']) {
      const box = (await page.getByTestId(id).boundingBox())!
      expect(box.x + box.width, id).toBeLessThanOrEqual(1920)
      expect(box.y + box.height, id).toBeLessThan(qr.y)
      // 빈칸 없는 문구도 상자 안에서 줄을 바꾼다 (넘치면 글자가 화면 밖으로 잘린다)
      expect(await page.getByTestId(id).evaluate(el => el.scrollWidth <= el.clientWidth), id).toBe(true)
    }
    expect(await smallestText(page)).toBeGreaterThanOrEqual(40)
    await page.waitForTimeout(800)
    await page.screenshot({ path: '../artifacts/display-eco-words.png' })
    // 안내 줄만 null로 없애고 나머지는 빼면 기본 문구 (새 판은 다음 상태를 받을 때 다시 받는다)
    text = { negative_hint: null }
    await page.reload()
    await expect(screen(page)).toHaveAttribute('data-scene', 'eco', { timeout: 6000 })
    await expect(page.getByTestId('display-eco-kicker')).toHaveText('우리가 함께 키우는 나무')
    await expect(page.getByTestId('display-eco-title')).toHaveText('분리수거가 잘 안 되고 있어요')
    await expect(page.getByTestId('display-eco-hint')).toHaveCount(0)
  } finally {
    clearInterval(bridge)
    await request.post('/api/v1/eco', { data: ecoBody(0, 0) })
  }
})

test('the demo borrows the eco words from the server so operators can preview them', async ({ page }) => {
  test.setTimeout(60000)
  await page.route('**/api/v1/display/content', route => route.fulfill({ json: {
    revision: 'e2e-demo-words', message: null, schedule: [], slides: [], sound: null, eco: { enabled: false, text: { initial: '나무가 자라는 중이에요' } },
    timing: { location_s: 40, slides_s: 30, eco_s: 15, count_s: 10, trash_alert_s: 10, passing_s: 8, passing_cooldown_s: 60 } } }))
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.goto('/display?demo')
  // 서버에서 나무를 꺼 두어도 데모는 늘 나무를 보인다 (미리 보기용)
  await expect(screen(page)).toHaveAttribute('data-scene', 'eco', { timeout: 45000 })
  await expect(page.getByTestId('display-eco')).toHaveAttribute('data-tree', 'initial')
  await expect(page.getByTestId('display-eco-title')).toHaveText('나무가 자라는 중이에요')
  await expect(page.getByTestId('display-eco-kicker')).toHaveText('우리가 함께 키우는 나무')
})
