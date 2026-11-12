import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { LiveProvider } from './live'
import { MockProvider } from './demo'

class Socket {
  static CLOSING = 2
  static instances: Socket[] = []
  readyState = 1
  onmessage?: (e: { data: string }) => void
  onerror?: () => void
  onclose?: () => void
  constructor(public url = '') { Socket.instances.push(this) }
  close() { this.readyState = 3; this.onclose?.() }
  send(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}
let visible: () => Promise<void>
let mono = 0
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = []; mono = 0
  vi.spyOn(performance, 'now').mockImplementation(() => mono)
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ ticket: 't1' }) })))
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:8000' })
  vi.stubGlobal('document', { visibilityState: 'visible', addEventListener: (_: string, fn: () => Promise<void>) => { visible = fn }, removeEventListener: vi.fn() })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function snapshot() { const mock = new MockProvider(); mock.start(); const result = mock.current.snapshot!; mock.dispose(); return result }
/** start()·재연결은 입장표를 먼저 받으므로 Promise를 비운 뒤에 소켓이 생긴다 */
async function begin(live: LiveProvider) { live.start(); await vi.advanceTimersByTimeAsync(0) }
it('reconnects after 1/2/4/8/10 seconds and resets backoff only on a snapshot', async () => {
  const live = new LiveProvider(); await begin(live)
  for (const delay of [1000, 2000, 4000, 8000, 10000, 10000]) {
    Socket.instances.at(-1)!.close()
    const count = Socket.instances.length
    await vi.advanceTimersByTimeAsync(delay - 1); expect(Socket.instances).toHaveLength(count)
    await vi.advanceTimersByTimeAsync(1); expect(Socket.instances).toHaveLength(count + 1)
  }
  Socket.instances.at(-1)!.send(snapshot())
  expect(live.current.serverProblem).toBe(false)
  Socket.instances.at(-1)!.close()
  const count = Socket.instances.length
  await vi.advanceTimersByTimeAsync(1000); expect(Socket.instances).toHaveLength(count + 1)
  live.dispose()
})
it('opens the stream with a one-time ticket from the authenticated HTTP API', async () => {
  const live = new LiveProvider(); await begin(live)
  expect(fetch).toHaveBeenCalledWith('/api/v1/stream-ticket', { method: 'POST', cache: 'no-store' })
  expect(Socket.instances[0].url).toBe('ws://localhost:8000/api/v1/stream?ticket=t1')
  live.dispose()
})
it('still tries the stream (and retries) when the ticket request fails', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
  const live = new LiveProvider(); await begin(live)
  expect(Socket.instances[0].url).toBe('ws://localhost:8000/api/v1/stream')
  Socket.instances[0].close()
  await vi.advanceTimersByTimeAsync(1000); expect(Socket.instances).toHaveLength(2)
  live.dispose()
})
it('uses configured timeout, ignores older revisions, and accepts a restarted server', async () => {
  const live = new LiveProvider(); await begin(live); const state = snapshot()
  state.settings.browser_delay_s = 4
  Socket.instances[0].send(state)
  mono = 3999; await vi.advanceTimersByTimeAsync(200); expect(live.current.serverProblem).toBe(false)
  Socket.instances[0].send({ ...state, revision: state.revision - 1 })
  expect(live.current.receivedMono).toBe(0)
  mono = 4000; await vi.advanceTimersByTimeAsync(200); expect(live.current.serverProblem).toBe(true)
  await vi.advanceTimersByTimeAsync(1000)
  Socket.instances.at(-1)!.send({ ...state, server_run_id: 'new-run', revision: 1 })
  expect(live.current.serverProblem).toBe(false)
  expect(live.current.snapshot?.server_run_id).toBe('new-run')
  live.dispose()
})
it('tab return masks old state until fresh HTTP response and dispose ignores old sockets', async () => {
  const live = new LiveProvider(); await begin(live); const state = snapshot(); Socket.instances[0].send(state)
  let finish!: (v: unknown) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const pending = visible()
  expect(live.current.serverProblem).toBe(true)
  finish({ ok: true, json: async () => ({ ...state, revision: state.revision + 1 }) })
  await pending
  expect(live.current.serverProblem).toBe(false)
  live.dispose()
  const revision = live.current.snapshot?.revision
  Socket.instances[0].send({ ...state, revision: 100 })
  expect(live.current.snapshot?.revision).toBe(revision)
})
it('late HTTP responses from before a server restart cannot overwrite fresh stream state', async () => {
  const live = new LiveProvider(); await begin(live); const state = snapshot(); Socket.instances[0].send(state)
  let finish!: (v: unknown) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { finish = resolve })))
  const pending = visible()
  Socket.instances[0].send({ ...state, server_run_id: 'restarted', revision: 1 })
  finish({ ok: true, json: async () => ({ ...state, revision: 100 }) })
  await pending
  expect(live.current.snapshot?.server_run_id).toBe('restarted')
  expect(live.current.serverProblem).toBe(false)
  live.dispose()
})
it('a chosen robot uses its own stream and HTTP state and ignores other robots', async () => {
  const live = new LiveProvider('LIMBO-02'); await begin(live); const state = snapshot()
  expect(Socket.instances[0].url).toBe('ws://localhost:8000/api/v1/stream?robot_id=LIMBO-02&ticket=t1')
  Socket.instances[0].send(state)   // LIMBO-01 상태: 버림
  expect(live.current.snapshot).toBeNull()
  Socket.instances[0].send({ ...state, robot_id: 'LIMBO-02' })
  expect(live.current.snapshot?.robot_id).toBe('LIMBO-02')
  const fetch = vi.fn(async () => ({ ok: true, json: async () => ({ ...state, robot_id: 'LIMBO-02', revision: state.revision + 1 }) }))
  vi.stubGlobal('fetch', fetch)
  await visible()
  expect((fetch.mock.calls[0] as unknown[])[0]).toBe('/api/v1/state?robot_id=LIMBO-02')
  live.dispose()
})
