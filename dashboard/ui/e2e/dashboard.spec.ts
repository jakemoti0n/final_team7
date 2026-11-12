import { test, expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { mkdirSync } from 'node:fs'
import { commandNames, resultLabels, type Command, type Outcome } from '../src/commands'
function telemetry() {
  const at = new Date().toISOString()
  return { schema_version: 1, robot_id: 'LIMBO-01', bridge_session_id: randomUUID(), sequence: 1, sent_at: at, source_clock: 'ros_sim', topics: Object.fromEntries(['odom', 'lidar_raw', 'lidar_filtered', 'camera_raw'].map(key => [key, { header_stamp: { sec: 0, nanosec: 0 }, last_received_at: at, age_ms: 0, received_count: 1, receive_hz: 10 }])), motion: { linear_speed_mps: 0, angular_velocity_radps: 0, last_received_at: at, age_ms: 0 } }
}
function telemetryV2(state: 'patrolling' | 'paused' | null = 'patrolling') {
  const base = telemetry()
  const at = base.sent_at
  return { ...base, schema_version: 2, patrol: state ? {
    state, waypoint_index: 0, waypoint_count: 2, waypoint_name: 'A', has_resumable_task: state === 'paused',
    reason: 'navigating', update_count: 1, last_received_at: at, age_ms: 0,
  } : { state: null, waypoint_index: null, waypoint_count: null, waypoint_name: null,
    has_resumable_task: null, reason: null, update_count: 0, last_received_at: null, age_ms: null },
    pose: { frame_id: 'map', x: 1, y: 1, yaw: 0, position_std_m: .1, last_received_at: at, age_ms: 0 } }
}
type LauncherState = 'idle' | 'running' | 'exited'
/** 텔레메트리 v3: v2 + Bridge가 띄운 순찰 노드 상태 */
function telemetryV3(state: 'patrolling' | 'paused' | 'waiting_localization' | null, launcher: LauncherState, session = randomUUID(), sequence = 1, updateCount = 1) {
  const base = telemetryV2(state as 'patrolling' | 'paused' | null)
  if (base.patrol.state) base.patrol.update_count = updateCount
  return { ...base, schema_version: 3, bridge_session_id: session, sequence,
    launcher: { commands: ['pause', 'resume', 'start', 'stop'], state: launcher, pid: launcher === 'idle' ? null : 123, exit_code: launcher === 'exited' ? 0 : null,
      waypoints_revision: launcher === 'idle' ? null : 'c'.repeat(64), log: launcher === 'idle' ? null : '/tmp/limbo-patrol-e2e.log', other_patrol_running: false } }
}
/** 가짜 Bridge: 명령을 가져가 claim하고 결과를 보고한다 */
async function bridgeTakes(request: import('@playwright/test').APIRequestContext, session: string, outcome: 'accepted' | 'rejected') {
  const next = await request.get(`/api/v1/commands/next?robot_id=LIMBO-01&bridge_session_id=${session}&wait_s=2`)
  expect(next.status()).toBe(200)
  const command = await next.json()
  expect((await request.post(`/api/v1/commands/${command.request_id}/claim`, { data: { robot_id: 'LIMBO-01', bridge_session_id: session } })).ok()).toBe(true)
  await request.post(`/api/v1/commands/${command.request_id}/result`, { data: { robot_id: 'LIMBO-01', bridge_session_id: session, request_id: command.request_id, outcome, message: outcome, service_latency_ms: 1, patrol_update_count_at_call: 1 } })
  return command
}
test('actual screen sends pause to the server, never shows success without confirmation, and demo never talks to actual APIs', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetryV2() })
  await page.goto('/')
  await expect(page.locator('.speed strong')).toHaveText('0.00')
  await expect(page.locator('.movement:not(.patrol-state)')).toContainText('정지 상태')
  await expect(page.locator('.map-card svg image')).toHaveCount(1)
  await expect(page.getByRole('button', { name: '프로그램 재시작' })).toHaveCount(0)
  await expect(page.locator('.controls .command')).toHaveCount(1)
  const pause = page.getByRole('button', { name: '주행 정지', exact: true })
  await expect(pause).toBeEnabled()
  await pause.click()
  await expect(page.locator('.result')).toContainText('정지 요청 중')
  const state = await (await request.get('/api/v1/state')).json()
  expect(state.command).toMatchObject({ command: 'pause', stage: 'queued' })
  // 로봇이 가져가지 않으면 5초 뒤 "실행 안 함" 실패 (expired). 성공으로 바뀌지 않는다
  await expect(page.locator('.result')).toContainText('정지 요청 실패', { timeout: 8000 })
  await expect(page.locator('.result')).toContainText('실행하지 않았습니다')
  await expect(page.locator('.result')).not.toContainText('정지 상태 확인됨')
  const before = await (await request.get('/api/v1/state')).json()
  const requests: string[] = []
  page.on('request', req => { if (req.url().includes('/api/')) requests.push(req.url()) })
  page.on('websocket', socket => requests.push(socket.url()))
  await page.goto('/demo')
  await expect(page.getByText('데모 데이터 · 실제 로봇을 제어하지 않습니다')).toBeVisible()
  await page.getByRole('button', { name: '주행 정지', exact: true }).click()
  await expect(page.locator('.result')).toContainText('정지 상태 확인됨')
  expect(requests).toEqual([])
  const after = await (await request.get('/api/v1/state')).json()
  expect(after.bridge.sequence).toBe(before.bridge.sequence)
  expect(after.command.request_id).toBe(before.command.request_id)
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
  await page.getByLabel('일시정지 결과', { exact: true }).selectOption('late')
  await page.getByRole('button', { name: '주행 정지', exact: true }).click()
  await expect(page.locator('.controls .command')).toBeDisabled()
  await expect(page.locator('.result')).toContainText('정지 여부 확인 불가')
  await page.waitForTimeout(2000)
  await expect(page.locator('.result')).not.toContainText('정지 상태 확인됨')
  await expect(page.locator('.alert-row')).toHaveCount(1)
  await page.getByRole('button', { name: '시나리오 초기화' }).click()
  await expect(page.locator('.result')).toHaveCount(0)
  await page.getByRole('button', { name: '주행 정지', exact: true }).click()
  await page.getByRole('button', { name: '진행 중 연결 끊기' }).click()
  await expect(page.locator('.result')).toContainText('정지 여부 확인 불가')
  await page.getByLabel('화면 상태', { exact: true }).selectOption('normal')
  await page.waitForTimeout(1000)
  await expect(page.locator('.result')).toHaveCount(0)
  await expect(page.locator('.alert-row')).toHaveCount(0)
})
test('single drive button follows the patrol state; sensor details stay folded', async ({ page }) => {
  await page.goto('/demo')
  await page.getByLabel('가상 순찰 상태').selectOption('patrolling')
  await expect(page.getByRole('button', { name: '주행 정지', exact: true })).toBeEnabled()
  await page.getByLabel('가상 순찰 상태').selectOption('empty')
  await expect(page.getByRole('button', { name: '주행 시작', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '주행 시작', exact: true }).click()
  await expect(page.getByRole('button', { name: '주행 정지', exact: true })).toBeEnabled()
  await page.getByLabel('가상 순찰 상태').selectOption('unknown')
  await expect(page.getByRole('button', { name: '주행 시작', exact: true })).toBeDisabled()
  await page.getByLabel('가상 순찰 상태').selectOption('paused')
  await expect(page.getByRole('button', { name: '주행 재개', exact: true })).toBeEnabled()
  await expect(page.locator('.controls .command')).toHaveCount(1)
  await expect(page.locator('details.reception table')).toBeHidden()
  await page.getByText('센서 수신 상세').click()
  await expect(page.locator('details.reception table')).toBeVisible()
  await page.getByLabel('화면 상태', { exact: true }).selectOption('partial')
  await expect(page.locator('.overall')).toContainText('확인 필요')
  await expect(page.locator('.overall')).toContainText('LiDAR 필터 결과 수신 지연')
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

for (const command of ['pause', 'resume'] as Command[]) {
  for (const outcome of ['success', 'reject', 'no_response', 'no_confirmation'] as Outcome[]) {
    test(`command ${command} outcome ${outcome}`, async ({ page }) => {
      await page.goto('/demo')
      await page.getByLabel('응답 제한 시간(초)', { exact: true }).fill('1')
      await page.getByLabel('상태 확인 제한 시간(초)', { exact: true }).fill('1.5')
      await page.getByLabel(`${commandNames[command]} 결과`, { exact: true }).selectOption(outcome)
      if (command === 'resume') await page.getByLabel('가상 순찰 상태').selectOption('paused')
      await page.getByRole('button', { name: command === 'pause' ? '주행 정지' : '주행 재개', exact: true }).click()
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
  await page.routeWebSocket(/\/api\/v1\/stream(\?|$)/, ws => { ws.send(JSON.stringify(state)) })
  await page.goto('/')
  await expect(page.locator('.connection')).toContainText('연결됨')
  await expect(page.getByRole('alert')).toContainText('서버 상태를 갱신할 수 없습니다', { timeout: 5000 })
  await request.post('/api/v1/telemetry', { data: telemetry() })
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await expect(page.locator('.connection')).toContainText('연결됨')
})

test('demo waypoints can be added, moved on the map, and deleted without API calls', async ({ page }) => {
  const apiRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/')) apiRequests.push(request.url()) })
  await page.goto('/demo')
  await page.getByLabel('가상 순찰 상태').selectOption('empty')
  const panel = page.getByRole('region', { name: 'Waypoint 목록' })
  await expect(panel.locator('li')).toHaveCount(10)
  await panel.getByRole('button', { name: '새 지점 만들기' }).click()
  await panel.getByLabel('이름').fill('새 지점 K')
  await page.locator('.map-card svg').click({ position: { x: 110, y: 110 } })
  await expect(panel).toContainText('선택한 위치:')
  await panel.getByRole('button', { name: '저장' }).click()
  await expect(panel.locator('li')).toHaveCount(11)
  await expect(page.locator('.map-card .waypoint')).toHaveCount(11)
  const row = panel.locator('li').filter({ hasText: '새 지점 K' })
  const before = await row.locator('small').textContent()
  await row.getByRole('button', { name: '위치 교체' }).click()
  await page.locator('.map-card svg').click({ position: { x: 190, y: 170 } })
  await panel.getByRole('button', { name: '저장' }).click()
  await expect(row.locator('small')).not.toHaveText(before!)
  await row.getByRole('button', { name: '삭제' }).click()
  await expect(panel.locator('li')).toHaveCount(10)
  expect(apiRequests).toEqual([])
})

test('live waypoint editor sends changes and updates the map without modifying the test route', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetryV2(null) })
  let doc = { revision: 'r1', waypoints: [
    { name: 'A', type: 'pass', x: 1, y: 1, yaw: 0, wait_sec: 0 },
    { name: 'B', type: 'stop', x: 2, y: 2, yaw: 0, wait_sec: 0 },
  ], file: 'route.yaml', applies: 'next_patrol_start' }
  const actions: string[] = []
  await page.route('**/api/v1/waypoints', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: doc })
    const data = route.request().postDataJSON()
    actions.push(data.action)
    expect(data.revision).toBe(doc.revision)
    const waypoints = data.action === 'add' ? [...doc.waypoints.slice(0, -1), { ...data.waypoint, yaw: 0, wait_sec: 0 }, doc.waypoints[doc.waypoints.length - 1]]
      : data.action === 'move' ? doc.waypoints.map(w => w.name === data.name ? { ...w, x: data.x, y: data.y } : w)
        : doc.waypoints.filter(w => w.name !== data.name)
    doc = { ...doc, revision: `r${actions.length + 1}`, waypoints }
    await route.fulfill({ json: doc })
  })
  await page.goto('/')
  const panel = page.getByRole('region', { name: 'Waypoint 목록' })
  await expect(panel).toContainText('route.yaml')
  await panel.getByRole('button', { name: '새 지점 만들기' }).click()
  await panel.getByLabel('이름').fill('C')
  await panel.getByLabel('종류').selectOption('pass')
  await page.locator('.map-card svg').click({ position: { x: 110, y: 110 } })
  await panel.getByRole('button', { name: '저장' }).click()
  await expect(panel.locator('li')).toHaveCount(3)
  await expect(panel).toContainText('순찰 노드를 다시 시작하면 적용됩니다')
  const row = panel.locator('li').filter({ hasText: 'C' })
  await row.getByRole('button', { name: '위치 교체' }).click()
  await page.locator('.map-card svg').click({ position: { x: 190, y: 170 } })
  await panel.getByRole('button', { name: '저장' }).click()
  await row.getByRole('button', { name: '삭제' }).click()
  await expect(panel.locator('li')).toHaveCount(2)
  expect(actions).toEqual(['add', 'move', 'delete'])
})

test('live waypoint names and drag order persist through the API', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetryV2(null) })
  let doc = { revision: 'r1', waypoints: [
    { name: 'A', type: 'pass', x: 1, y: 1, yaw: 90, wait_sec: 2 },
    { name: 'B', type: 'stop', x: 2, y: 2, yaw: 30, wait_sec: 3 },
    { name: 'C', type: 'stop', x: 3, y: 3, yaw: 0, wait_sec: 0 },
  ], file: 'route.yaml', applies: 'next_patrol_start' }
  const actions: string[] = []
  await page.route('**/api/v1/waypoints', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: doc })
    const data = route.request().postDataJSON()
    expect(data.revision).toBe(doc.revision)
    actions.push(data.action)
    const points = data.action === 'rename' ? doc.waypoints.map(w => w.name === data.name ? { ...w, name: data.new_name } : w)
      : data.order.map((name: string) => doc.waypoints.find(w => w.name === name)!)
    doc = { ...doc, revision: `r${actions.length + 1}`, waypoints: points }
    await route.fulfill({ json: doc })
  })
  await page.goto('/')
  const panel = page.getByRole('region', { name: 'Waypoint 목록' })
  await expect(panel.locator('li')).toHaveCount(3)
  await panel.locator('li').filter({ hasText: 'B' }).getByRole('button', { name: '이름 변경' }).click()
  await panel.getByLabel('새 이름').fill('로비')
  await panel.getByRole('button', { name: '저장' }).click()
  await expect(panel.locator('li').nth(1)).toContainText('로비')
  await panel.getByRole('button', { name: 'A 순서 끌어서 변경' }).dragTo(panel.locator('li').nth(1))
  await expect(panel.locator('li').first()).toContainText('로비')
  await expect(panel.locator('li').nth(1)).toContainText('A')
  await expect(page.locator('.map-card .waypoint').first()).toContainText('로비')
  expect(actions).toEqual(['rename', 'reorder'])
  expect(doc.waypoints[0]).toMatchObject({ name: '로비', yaw: 30, wait_sec: 3 })
})

test('live drive start sends a start command with the saved route and confirms from telemetry', async ({ page, request }) => {
  const session = randomUUID()
  expect((await request.post('/api/v1/telemetry', { data: telemetryV3(null, 'idle', session) })).ok()).toBe(true)
  await page.goto('/')
  await page.getByRole('button', { name: '주행 시작', exact: true }).click()
  await expect(page.getByRole('button', { name: '주행 시작 중' })).toBeDisabled()
  const command = await bridgeTakes(request, session, 'accepted')
  expect(command.command).toBe('start')
  expect(command.route.waypoints.at(-1).type).toBe('stop')                 // 서버 YAML 경로가 실림
  await expect(page.locator('.result')).toContainText('순찰 노드를 실행했습니다')
  expect((await request.post('/api/v1/telemetry', { data: telemetryV3('patrolling', 'running', session, 2, 2) })).ok()).toBe(true)
  await expect(page.locator('.result')).toContainText('순찰 시작 확인됨')
  await expect(page.getByRole('button', { name: '주행 정지', exact: true })).toBeEnabled()
})

test('waypoint drag handle appears to the right of row actions', async ({ page }) => {
  await page.goto('/demo')
  const row = page.getByRole('region', { name: 'Waypoint 목록' }).locator('li').first()
  const name = await row.locator('.waypoint-name').boundingBox()
  const handle = await row.getByRole('button', { name: 'A 순서 끌어서 변경' }).boundingBox()
  const bounds = await row.boundingBox()
  expect(name).not.toBeNull()
  expect(handle).not.toBeNull()
  expect(bounds).not.toBeNull()
  expect(handle!.x).toBeGreaterThan(name!.x + name!.width - 1)
  expect(bounds!.x + bounds!.width - handle!.x - handle!.width).toBeLessThan(16)
})


test('waypoint controls lock during patrol and unlock after termination in demo', async ({ page }) => {
  await page.goto('/demo')
  const panel = page.getByRole('region', { name: 'Waypoint 목록' })
  const add = panel.getByRole('button', { name: '새 지점 만들기' })
  await expect(add).toBeDisabled()
  await expect(panel.locator('.waypoint-add').locator('..')).toHaveAttribute('title', '주행 완료 후 변경 가능합니다')
  await expect(panel.getByRole('button', { name: '이름 변경' }).first()).toBeDisabled()
  await expect(panel.getByRole('button', { name: 'A 순서 끌어서 변경' })).toBeDisabled()
  await page.getByLabel('가상 순찰 상태').selectOption('paused')
  await expect(add).toBeDisabled()
  await page.getByRole('button', { name: '순찰 종료' }).click()
  await expect(add).toBeEnabled()
  await expect(page.getByRole('button', { name: '주행 시작', exact: true })).toBeEnabled()
})

test('live patrol termination sends a stop command; only Bridge-started nodes can be stopped', async ({ page, request }) => {
  const session = randomUUID()
  await request.post('/api/v1/telemetry', { data: telemetryV3('patrolling', 'running', session) })
  await page.goto('/')
  const stop = page.getByRole('button', { name: '순찰 종료' })
  await expect(stop).toBeEnabled()
  await stop.click()
  await expect(page.getByRole('button', { name: '순찰 종료 중' })).toBeDisabled()
  expect((await bridgeTakes(request, session, 'accepted')).command).toBe('stop')
  await expect(page.locator('.result')).toContainText('종료 신호를 보냈습니다')
  await request.post('/api/v1/telemetry', { data: telemetryV3('patrolling', 'exited', session, 2) })
  await expect(page.locator('.result')).toContainText('순찰 종료 확인됨')
  // 노드가 끝났으면 남은 순찰 상태는 오래된 것 → 다시 시작 가능, 종료는 잠김
  await expect(page.getByRole('button', { name: '주행 시작', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '순찰 종료' })).toBeDisabled()
})

test('an older Bridge without launcher locks start and stop but keeps pause', async ({ page, request }) => {
  await request.post('/api/v1/telemetry', { data: telemetryV2('patrolling') })
  await page.goto('/')
  await expect(page.getByRole('button', { name: '주행 정지', exact: true })).toBeEnabled()
  await expect(page.getByRole('button', { name: '순찰 종료' })).toBeDisabled()
  await expect(page.locator('.patrol-stop').locator('..')).toHaveAttribute('title', /Bridge를 업데이트/)
  await request.post('/api/v1/telemetry', { data: telemetryV2(null) })
  await expect(page.getByRole('button', { name: '주행 시작', exact: true })).toBeDisabled()
  await expect(page.locator('#control-reason')).toContainText('Bridge를 업데이트')
})

test('robot name in the header opens the robot list and switches the whole screen to the chosen robot', async ({ page, request }) => {
  const other = 'LIMBO-E2E-2'
  expect((await request.post('/api/v1/telemetry', { data: telemetryV2('patrolling') })).ok()).toBe(true)
  expect((await request.post('/api/v1/telemetry', { data: { ...telemetryV2('paused'), robot_id: other } })).ok()).toBe(true)
  await page.goto('/')
  const picker = page.getByRole('button', { name: /로봇 선택/ })
  await expect(picker).toHaveText(/LIMBO-01/)
  await expect(page.locator('.patrol-state')).toContainText('순찰 중')
  await picker.click()
  const list = page.getByRole('listbox', { name: '로봇 목록' })
  await expect(list.getByRole('option')).toHaveCount(await (await request.get('/api/v1/robots')).json().then(b => b.robots.length))
  await expect(list.getByRole('option', { name: /LIMBO-01/ })).toHaveAttribute('aria-selected', 'true')
  await list.getByRole('option', { name: new RegExp(other) }).click()
  await expect(list).toHaveCount(0)
  await expect(picker).toHaveText(new RegExp(other))
  await expect(page).toHaveURL(new RegExp(`\\?robot=${other}`))
  await expect(page.locator('.patrol-state')).toContainText('일시정지')
  await expect(page.locator('footer')).toContainText(other)
  // 새로 고쳐도 고른 로봇 유지, Esc로 목록 닫힘
  await page.reload()
  await expect(picker).toHaveText(new RegExp(other))
  await picker.click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('listbox')).toHaveCount(0)
  // 서버가 모르는 로봇이 주소에 있으면 기본 로봇으로 돌아간다
  await page.goto('/?robot=NOT-THERE')
  await expect(picker).toHaveText(/LIMBO-01/)
})

test('other robots on the same map are drawn and clicking one switches to it', async ({ page, request }) => {
  const other = 'LIMBO-E2E-3'
  expect((await request.post('/api/v1/telemetry', { data: telemetryV2('patrolling') })).ok()).toBe(true)
  const second = telemetryV2('paused')
  expect((await request.post('/api/v1/telemetry', { data: { ...second, robot_id: other, pose: { ...second.pose, x: 2, y: 1.5, yaw: 1 } } })).ok()).toBe(true)
  await page.goto('/')
  const marker = page.locator('.map-card .robot.other', { has: page.locator('text', { hasText: other }) })
  await expect(marker).toHaveCount(1)
  await expect(page.locator('.map-legend')).toContainText('다른 로봇 (누르면 전환)')
  await expect(page.locator('.map-card .robot:not(.other)')).toHaveCount(1)   // 선택한 로봇은 따로 그림
  await marker.locator('.hit').click()   // 화살표 둘레 누름 영역
  await expect(page.getByRole('button', { name: /로봇 선택/ })).toHaveText(new RegExp(other))
  await expect(page.locator('.patrol-state')).toContainText('일시정지')
  // 이제 LIMBO-01이 다른 로봇으로 보인다
  await expect(page.locator('.map-card .robot.other', { has: page.locator('text', { hasText: 'LIMBO-01' }) })).toHaveCount(1)
})
