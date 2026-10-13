import { expect, it, vi } from 'vitest'
import { LiveControl, fromServer, lockReason, resumeReason, stageShapes } from './control'
import { headingDeg, isMapInfo, toPixel, uncertaintyPx } from './map'
import { MockProvider } from './demo'
import { overall } from './App'
import type { ServerCommand, ServerStage, Snapshot, View } from './types'

function view(change: (s: Snapshot) => void = () => {}, serverProblem = false): View {
  const mock = new MockProvider(); mock.start(); const snapshot = structuredClone(mock.current.snapshot!); mock.dispose()
  snapshot.patrol = { state: 'paused', waypoint_index: 2, waypoint_count: 10, waypoint_name: 'C', has_resumable_task: true, reason: '', update_count: 3, last_received_at: snapshot.server_utc, age_s: 0 }
  change(snapshot)
  return { snapshot, serverProblem, receivedMono: 0 }
}
const command = (stage: ServerStage, message = ''): ServerCommand => ({ request_id: 'r1', command: 'pause', stage, message, issued_at: '2026-10-13T00:00:00.000Z', updated_at: '2026-10-13T00:00:01.000Z' })

it('only confirmed is success; explicit failures are failed; the rest cannot be confirmed', () => {
  const expected: Record<ServerStage, string> = { queued: 'pending', delivered: 'pending', accepted: 'pending', confirmed: 'success', rejected: 'failed', service_unavailable: 'failed', no_response: 'unknown', expired: 'unknown', unconfirmed: 'unknown', connection_lost: 'unknown' }
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
  const before = view()
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
  await offline.send(before, 'resume')
  expect(offline.current(before)?.result).toBe('failed')
  expect(post).toHaveBeenCalledTimes(3)
  await new LiveControl(changed, post as unknown as typeof fetch).send(view(s => { s.patrol!.state = 'patrolling' }), 'resume')
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
