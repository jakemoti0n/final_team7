import { expect, it, vi } from 'vitest'
import { LiveControl, enrollReason, followStartReason, followStopReason, fromServer, lockReason, pauseReason, reasonFor, resumeReason, stageShapes } from './control'
import { headingDeg, isMapInfo, toPixel, uncertaintyPx } from './map'
import { MockProvider } from './demo'
import { followLabel, overall, patrolLabel } from './App'
import type { FollowInfo, ServerCommand, ServerStage, Snapshot, View } from './types'

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

// ---- 따라가기 (PROJECT.md 2-9 3단계) ----
const followInfo = (change: Partial<FollowInfo> = {}): FollowInfo => ({ state: 'idle', active: false, enrolled: true, visible: true, target_id: -1, distance_m: 0, reason: 'idle', elapsed_s: 2, lost_s: 0, update_count: 4, last_received_at: '2026-10-22T00:00:00.000Z', age_s: 0, ...change })
it('follow start needs enrollment and not already following; stop needs following; enroll is blocked while following', () => {
  expect(followStartReason(view(s => { s.follow = followInfo() }), '')).toBe('')
  expect(followStartReason(view(s => { s.follow = followInfo({ enrolled: false }) }), '')).toBe('운용자를 먼저 등록하세요')
  expect(followStartReason(view(s => { s.follow = followInfo({ visible: false }) }), '')).toBe('')           // 보이는지는 잠그지 않음 (노드가 거절)
  expect(followStartReason(view(s => { s.follow = followInfo({ state: 'following', active: true }) }), '')).toBe('이미 따라가는 중입니다')
  expect(followStartReason(view(s => { s.follow = null }), '')).toBe('따라가기 상태를 확인할 수 없습니다')
  expect(followStartReason(view(s => { s.follow = { ...followInfo(), state: null, active: null, enrolled: null, update_count: 3 } }), '')).toBe('따라가기 프로그램 상태를 확인할 수 없습니다')
  expect(followStartReason(view(s => { s.follow = followInfo() }), '잠김')).toBe('잠김')
  expect(followStopReason(view(s => { s.follow = followInfo({ state: 'holding', active: true }) }), '')).toBe('')
  expect(followStopReason(view(s => { s.follow = followInfo() }), '')).toBe('따라가는 중이 아닙니다')
  expect(enrollReason(view(s => { s.follow = followInfo({ enrolled: false }) }), '')).toBe('')
  expect(enrollReason(view(s => { s.follow = followInfo({ state: 'following', active: true }) }), '')).toBe('따라가는 중에는 등록할 수 없습니다')
  expect(reasonFor('follow_stop', view(s => { s.follow = followInfo({ state: 'following', active: true }) }), '')).toBe('')
})
it('patrol resume is locked while following; pause is not', () => {
  const following = view(s => { s.follow = followInfo({ state: 'following', active: true }); s.patrol!.state = 'paused' })
  expect(resumeReason(following, '')).toBe('따라가기 중입니다. 먼저 따라가기를 정지하세요')
  expect(resumeReason(view(s => { s.follow = followInfo() }), '')).toBe('')
  expect(pauseReason(view(s => { s.follow = followInfo({ state: 'following', active: true }); s.patrol!.state = 'patrolling' }), '')).toBe('')
})
it('follow labels: standing near the operator is still following; lost shows seconds; ended shows why', () => {
  expect(followLabel(followInfo({ state: 'following', active: true, reason: 'moving' }))).toMatchObject({ label: '따라가는 중', tone: 'good' })
  expect(followLabel(followInfo({ state: 'following', active: true, reason: 'near_hold' })).label).toContain('정지')
  expect(followLabel(followInfo({ state: 'holding', active: true, reason: 'target_lost', lost_s: 6.8 }))).toMatchObject({ label: '운용자 찾는 중 · 6초', tone: 'warn' })
  expect(followLabel(followInfo({ state: 'stopped', reason: 'lost_timeout' }))).toMatchObject({ label: '끝남 · 운용자 놓침', tone: 'warn' })
  expect(followLabel(followInfo({ state: 'stopped', reason: 'stop_requested' }))).toMatchObject({ label: '끝남 · 정지 명령', tone: 'neutral' })
  expect(followLabel(followInfo({ state: 'stopped', reason: 'nav_aborted' })).label).toBe('끝남 · 주행 실패 (aborted)')
  expect(followLabel(followInfo()).label).toBe('대기 중')
})
it('live control sends follow commands through the same endpoint and rejects locked ones locally', async () => {
  const calls: string[] = []
  const post = vi.fn(async (_url: string, init?: RequestInit) => { calls.push(JSON.parse(init!.body as string).command); return new Response(JSON.stringify({ request_id: 'r9', command: 'follow_start', issued_at: '2026-10-22T00:00:00.000Z', stage: 'queued' }), { status: 202 }) })
  const live = new LiveControl(() => {}, post as unknown as typeof fetch)
  await live.send(view(s => { s.follow = followInfo({ enrolled: false }) }), 'follow_start')
  expect(calls).toEqual([])                                                   // 미등록: 보내지 않음
  await live.send(view(s => { s.follow = followInfo() }), 'follow_start')
  expect(calls).toEqual(['follow_start'])
  expect(live.current(view(s => { s.follow = followInfo() }))?.command).toBe('follow_start')
})
