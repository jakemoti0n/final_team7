import { expect, it, vi } from 'vitest'
import { LiveControl, driveControl, fromServer, lockReason, pauseReason, resumeReason, stageShapes, startReason, stopReason, waypointLocked } from './control'
import { headingDeg, isMapInfo, toPixel, uncertaintyPx } from './map'
import { MockProvider } from './demo'
import { overall, patrolLabel } from './App'
import type { ServerCommand, ServerStage, Snapshot, View } from './types'

function view(change: (s: Snapshot) => void = () => {}, serverProblem = false): View {
  const mock = new MockProvider(); mock.start(); const snapshot = structuredClone(mock.current.snapshot!); mock.dispose()
  snapshot.patrol = { state: 'paused', waypoint_index: 2, waypoint_count: 10, waypoint_name: 'C', has_resumable_task: true, reason: '', update_count: 3, last_received_at: snapshot.server_utc, age_s: 0 }
  change(snapshot)
  return { snapshot, serverProblem, receivedMono: 0 }
}
const command = (stage: ServerStage, message = ''): ServerCommand => ({ request_id: 'r1', command: 'pause', stage, message, issued_at: '2026-10-13T00:00:00.000Z', updated_at: '2026-10-13T00:00:01.000Z' })

it('only confirmed is success; explicit failures are failed; the rest cannot be confirmed', () => {
  const expected: Record<ServerStage, string> = { queued: 'pending', delivered: 'pending', accepted: 'pending', confirmed: 'success', rejected: 'failed', service_unavailable: 'failed', no_response: 'unknown', expired: 'failed', unconfirmed: 'unknown', connection_lost: 'unknown' }
  for (const stage of Object.keys(stageShapes) as ServerStage[]) expect(fromServer(command(stage)).result).toBe(expected[stage])
  expect(fromServer(command('queued')).stages).toEqual(['running', 'waiting', 'waiting'])
  expect(fromServer(command('accepted')).stages).toEqual(['done', 'done', 'running'])
  expect(fromServer(command('rejected', 'already paused')).detail).toContain('already paused')
})
it('controls lock without a connection or while a request is pending', () => {
  expect(lockReason(view(), null)).toBe('')
  expect(lockReason(view(s => { s.bridge.status = 'delayed' }), null)).toContain('연결')
  expect(lockReason(view(undefined, true), null)).toContain('연결')
  expect(lockReason(view(), fromServer(command('delivered')))).toBe('요청을 처리하고 있습니다')
  expect(lockReason(view(), fromServer(command('no_response')))).toBe('')
})
it('pause locks only when the patrol node says it is already paused', () => {
  expect(pauseReason(view(), '')).toBe('이미 일시정지 상태입니다')
  expect(pauseReason(view(s => { s.patrol!.state = 'pausing' }), '')).toBe('이미 일시정지 상태입니다')
  expect(pauseReason(view(s => { s.patrol!.state = 'patrolling' }), '')).toBe('')
  expect(pauseReason(view(s => { s.patrol = null }), '')).toBe('')            // 모르면 누를 수 있음
  expect(pauseReason(view(s => { s.patrol!.state = 'patrolling' }), '잠김')).toBe('잠김')
})
it('resume is allowed only by has_resumable_task, never by speed', () => {
  expect(resumeReason(view(), '')).toBe('')
  expect(resumeReason(view(s => { s.patrol!.state = 'patrolling' }), '')).toBe('이미 순찰 중입니다')
  expect(resumeReason(view(s => { s.patrol!.has_resumable_task = false; s.motion.status = 'stopped' }), '')).toBe('재개할 작업이 없습니다')
  expect(resumeReason(view(s => { s.patrol = null }), '')).toBe('순찰 상태를 확인할 수 없습니다')
  expect(resumeReason(view(s => { s.patrol!.state = null; s.patrol!.has_resumable_task = false as never }), '')).toBe('순찰 프로그램 상태를 확인할 수 없습니다')
  expect(resumeReason(view(), '잠김')).toBe('잠김')
})
it('live control: sending, then the server snapshot takes over; refusals are shown and never resent', async () => {
  const changed = vi.fn()
  const post = vi.fn().mockResolvedValue(new Response(JSON.stringify({ request_id: 'r1', command: 'pause', stage: 'queued', issued_at: '2026-10-13T00:00:00.000Z' }), { status: 202 }))
  const control = new LiveControl(changed, post as unknown as typeof fetch)
  const before = view(s => { s.patrol!.state = 'patrolling' })   // 일시정지 보낼 수 있는 상태
  const paused = view()
  const sending = control.send(before, 'pause')
  expect(control.current(before)?.detail).toContain('보내고 있습니다')
  await sending
  expect(post).toHaveBeenCalledTimes(1)
  expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ command: 'pause' })
  expect(control.current(before)?.stages).toEqual(['running', 'waiting', 'waiting'])
  expect(control.current(view(s => { s.command = command('confirmed') }))?.result).toBe('success')
  post.mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'bridge_not_connected', message: '' } }), { status: 409 }))
  const fresh = new LiveControl(changed, post as unknown as typeof fetch)
  await fresh.send(before, 'pause')
  expect(fresh.current(before)?.result).toBe('failed')
  expect(fresh.current(before)?.detail).toContain('연결되어 있지 않아')
  post.mockRejectedValueOnce(new Error('offline'))
  const offline = new LiveControl(changed, post as unknown as typeof fetch)
  await offline.send(paused, 'resume')
  expect(offline.current(paused)?.result).toBe('failed')
  expect(post).toHaveBeenCalledTimes(3)
  await new LiveControl(changed, post as unknown as typeof fetch).send(before, 'resume')
  await new LiveControl(changed, post as unknown as typeof fetch).send(paused, 'pause')
  expect(post).toHaveBeenCalledTimes(3) // 잠긴 버튼은 서버를 부르지 않는다
})
it('map pixels: origin is bottom-left, y grows up; heading and uncertainty', () => {
  const map = { resolution: .05, origin: [-7.5, -7.5, 0], width: 300, height: 300, image: null, waypoints: [] }
  expect(toPixel(map, -7.5, -7.5)).toEqual([0, 300])
  expect(toPixel(map, 0, 0)).toEqual([150, 150])
  expect(toPixel(map, 7.5, 7.5)).toEqual([300, 0])
  expect(headingDeg(Math.PI / 2)).toBeCloseTo(-90)
  expect(uncertaintyPx(map, .1)).toBeCloseTo(4)
  expect(uncertaintyPx(map, null)).toBe(0)
  expect(isMapInfo(map)).toBe(true); expect(isMapInfo({ resolution: 0 })).toBe(false)
})
it('one-line summary: normal / check needed with the reason / disconnected', () => {
  expect(overall(view()).label).toBe('정상')
  expect(overall(view(s => { s.topics.camera_raw.status = 'delayed' }))).toMatchObject({ label: '확인 필요', detail: '카메라 원본 수신 지연' })
  expect(overall(view(s => { s.bridge.status = 'disconnected' })).label).toBe('연결 끊김')
  expect(overall(view(undefined, true)).label).toBe('연결 끊김')
})
it('patrol card: retrying and stopped after navigation failure are shown apart from normal states', () => {
  expect(patrolLabel('patrolling', 'navigation failed, retry 1/2')).toMatchObject({ label: '순찰 중 · 이동 다시 시도 (1/2)', tone: 'warn' })
  expect(patrolLabel('paused', 'navigation failed')).toMatchObject({ label: '이동 실패 · 확인 후 재개', tone: 'warn' })
  expect(patrolLabel('paused', 'paused by request')).toMatchObject({ label: '일시정지', note: '' })
  expect(patrolLabel('patrolling', 'lap 2 started')).toMatchObject({ label: '순찰 중', tone: 'good' })
})

const stopped = (s: Snapshot) => { s.launcher = { ...s.launcher!, state: 'exited', exit_code: 0 }; s.patrol_running = false }
it('one drive control maps state to start, stop, and resume', () => {
  expect(driveControl(view(), null)).toEqual({ action: 'resume', reason: '' })
  expect(driveControl(view(s => { s.patrol!.state = 'patrolling' }), null)).toEqual({ action: 'pause', reason: '' })
  // Bridge가 띄운 노드가 끝났으면 남은 순찰 상태는 오래된 것 → 시작
  expect(driveControl(view(s => { s.patrol!.state = 'patrolling'; stopped(s) }), null)).toEqual({ action: 'start', reason: '' })
  expect(driveControl(view(s => { s.patrol!.state = 'completed'; stopped(s) }), null)).toEqual({ action: 'start', reason: '' })
  expect(driveControl(view(s => { s.patrol!.state = null; s.patrol!.update_count = 0; stopped(s) }), null)).toEqual({ action: 'start', reason: '' })
  expect(driveControl(view(s => { s.patrol!.state = null; s.patrol!.update_count = 3; stopped(s) }), null)).toEqual({ action: 'start', reason: '' })
  expect(driveControl(view(s => { s.patrol = null }), null).reason).toContain('확인할 수 없습니다')
  // 노드는 떴는데 아직 순찰 상태를 안 냄 → 시작 잠금
  expect(driveControl(view(s => { s.patrol!.state = null }), null)).toEqual({ action: 'start', reason: '이미 순찰 노드가 실행 중입니다' })
  // 시작 요청 처리 중에는 "주행 시작 중"
  const starting = fromServer({ ...command('accepted'), command: 'start' })
  expect(driveControl(view(s => { s.patrol!.state = 'waiting_localization' }), starting)).toEqual({ action: 'start', reason: '요청을 처리하고 있습니다' })
})
it('start and stop need a Bridge that reports the launcher; stop only for its own node', () => {
  expect(startReason(view(stopped), '')).toBe('')
  expect(startReason(view(), '')).toBe('이미 순찰 노드가 실행 중입니다')
  expect(startReason(view(s => { s.launcher = null }), '')).toContain('Bridge를 업데이트')
  expect(startReason(view(s => { s.launcher!.commands = ['pause', 'resume'] }), '')).toContain('Bridge를 업데이트')
  expect(stopReason(view(), '')).toBe('')
  expect(stopReason(view(stopped), '')).toBe('실행 중인 순찰 노드가 없습니다')
  expect(stopReason(view(s => { stopped(s); s.launcher!.other_patrol_running = true }), '')).toContain('다른 곳에서 띄운')
  expect(stopReason(view(s => { s.launcher = null }), '')).toContain('Bridge를 업데이트')
  expect(stopReason(view(), '잠김')).toBe('잠김')
})
it('waypoint editing follows the server lock and pending start/stop', () => {
  expect(waypointLocked(view(), null)).toBe(true)
  expect(waypointLocked(view(stopped), null)).toBe(false)
  expect(waypointLocked(view(stopped), fromServer({ ...command('queued'), command: 'start' }))).toBe(true)
  expect(waypointLocked(view(stopped), fromServer({ ...command('queued'), command: 'pause' }))).toBe(false)
  expect(waypointLocked(view(s => { delete s.patrol_running }), null)).toBe(true)   // 이전 서버: 순찰 상태로 판단
})
it('live control sends start and stop through the command API', async () => {
  const post = vi.fn().mockResolvedValue(new Response(JSON.stringify({ request_id: 'r2', command: 'start', stage: 'queued', issued_at: '2026-10-13T00:00:00.000Z' }), { status: 202 }))
  const control = new LiveControl(vi.fn(), post as unknown as typeof fetch)
  await control.send(view(stopped), 'start')
  expect(post.mock.calls[0][0]).toBe('/api/v1/commands')
  expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ command: 'start' })
  post.mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: 'bridge_unsupported', message: '' } }), { status: 409 }))
  const refused = new LiveControl(vi.fn(), post as unknown as typeof fetch)
  await refused.send(view(), 'stop')
  expect(refused.current(view())?.detail).toContain('relay_prog를 업데이트')
  await new LiveControl(vi.fn(), post as unknown as typeof fetch).send(view(), 'start')   // 잠김: 보내지 않음
  expect(post).toHaveBeenCalledTimes(2)
  expect(fromServer({ ...command('rejected', 'patrol_already_running'), command: 'start' }).detail).toContain('실행하지 못했습니다. 사유: patrol_already_running')
})
