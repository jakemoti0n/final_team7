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
  constructor() { Socket.instances.push(this) }
  close() { this.readyState = 3; this.onclose?.() }
  send(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}
let visible: () => Promise<void>
let mono = 0
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = []; mono = 0
  vi.spyOn(performance, 'now').mockImplementation(() => mono)
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:8000' })
  vi.stubGlobal('document', { visibilityState: 'visible', addEventListener: (_: string, fn: () => Promise<void>) => { visible = fn }, removeEventListener: vi.fn() })
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function snapshot() { const mock = new MockProvider(); mock.start(); const result = mock.current.snapshot!; mock.dispose(); return result }
it('reconnects after 1/2/4/8/10 seconds and resets backoff only on a snapshot', () => {
  const live = new LiveProvider(); live.start()
  for (const delay of [1000, 2000, 4000, 8000, 10000, 10000]) {
    Socket.instances.at(-1)!.close()
    const count = Socket.instances.length
    vi.advanceTimersByTime(delay - 1); expect(Socket.instances).toHaveLength(count)
    vi.advanceTimersByTime(1); expect(Socket.instances).toHaveLength(count + 1)
  }
  Socket.instances.at(-1)!.send(snapshot())
  expect(live.current.serverProblem).toBe(false)
  Socket.instances.at(-1)!.close()
  const count = Socket.instances.length
  vi.advanceTimersByTime(1000); expect(Socket.instances).toHaveLength(count + 1)
  live.dispose()
})
it('uses configured timeout, ignores older revisions, and accepts a restarted server', () => {
  const live = new LiveProvider(); live.start(); const state = snapshot()
  state.settings.browser_delay_s = 4
  Socket.instances[0].send(state)
  mono = 3999; vi.advanceTimersByTime(200); expect(live.current.serverProblem).toBe(false)
  Socket.instances[0].send({ ...state, revision: state.revision - 1 })
  expect(live.current.receivedMono).toBe(0)
  mono = 4000; vi.advanceTimersByTime(200); expect(live.current.serverProblem).toBe(true)
  vi.advanceTimersByTime(1000)
  Socket.instances.at(-1)!.send({ ...state, server_run_id: 'new-run', revision: 1 })
  expect(live.current.serverProblem).toBe(false)
  expect(live.current.snapshot?.server_run_id).toBe('new-run')
  live.dispose()
})
it('tab return masks old state until fresh HTTP response and dispose ignores old sockets', async () => {
  const live = new LiveProvider(); live.start(); const state = snapshot(); Socket.instances[0].send(state)
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
  const live = new LiveProvider(); live.start(); const state = snapshot(); Socket.instances[0].send(state)
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
