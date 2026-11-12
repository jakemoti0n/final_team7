import type { Provider, Snapshot, View } from './types'

export const backoff = [1000, 2000, 4000, 8000, 10000]
/** 서버 주소에 붙일 로봇 선택. 비우면 서버의 기본 로봇 */
export function robotQuery(robotId: string, first = true) { return robotId ? `${first ? '?' : '&'}robot_id=${encodeURIComponent(robotId)}` : '' }
export class LiveProvider implements Provider {
  current: View = { snapshot: null, serverProblem: false, receivedMono: performance.now() }
  private listeners = new Set<(v: View) => void>()
  private socket?: WebSocket
  private retry?: ReturnType<typeof setTimeout>
  private watch?: ReturnType<typeof setInterval>
  private attempt = 0
  private stopped = false
  private generation = 0
  private controller?: AbortController
  /** robotId: 이 화면이 보는 로봇. 다른 로봇의 상태가 오면 버린다 */
  constructor(private robotId = '') {}
  subscribe = (fn: (view: View) => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  private emit() { this.listeners.forEach(fn => fn(this.current)) }
  private fail() { this.current = { ...this.current, serverProblem: true }; this.emit() }
  private accept(value: Snapshot) {
    if (!value?.server_run_id || !Number.isInteger(value.revision) || !value.settings || !value.topics || !value.motion || !value.bridge) throw new Error('invalid snapshot')
    if (this.robotId && value.robot_id !== this.robotId) return
    const old = this.current.snapshot
    if (old?.server_run_id === value.server_run_id && value.revision <= old.revision) return
    this.current = { snapshot: value, serverProblem: false, receivedMono: performance.now() }
    this.attempt = 0
    this.emit()
  }
  private connect = async () => {
    if (this.stopped) return
    const generation = this.generation
    // 일회용 입장표를 먼저 받는다. Safari(iPhone)는 WebSocket에 basic auth를 싣지 않아
    // 입장표 없이 열면 401 → 로그인 창이 반복된다. 받지 못하면 그대로 열어 보고, 실패하면 재시도한다
    let ticket = ''
    try {
      const response = await fetch('/api/v1/stream-ticket', { method: 'POST', cache: 'no-store' })
      if (response.ok) ticket = String((await response.json())?.ticket ?? '')
    } catch { /* 아래 WebSocket이 실패하면 onclose가 재시도한다 */ }
    if (this.stopped || generation !== this.generation) return
    const query = robotQuery(this.robotId) + (ticket ? `${this.robotId ? '&' : '?'}ticket=${encodeURIComponent(ticket)}` : '')
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/stream${query}`)
    this.socket = ws
    ws.onmessage = event => {
      if (this.stopped || generation !== this.generation || this.socket !== ws) return
      try { this.accept(JSON.parse(event.data)) } catch { this.fail(); ws.close() }
    }
    ws.onerror = () => { if (!this.stopped && this.socket === ws) { this.fail(); ws.close() } }
    ws.onclose = () => {
      if (this.stopped || generation !== this.generation || this.socket !== ws) return
      this.fail()
      this.retry = setTimeout(() => { void this.connect() }, backoff[Math.min(this.attempt++, backoff.length - 1)])
    }
  }
  private refresh = async () => {
    if (document.visibilityState !== 'visible' || this.stopped) return
    this.fail() // 탭으로 돌아왔다고 예전 스냅샷을 현재 상태로 인정하지 않는다
    this.controller?.abort()
    const controller = new AbortController()
    this.controller = controller
    const generation = this.generation
    const snapshotAtFetch = this.current.snapshot
    const timeout = setTimeout(() => controller.abort(), 3000)
    try {
      const response = await fetch(`/api/v1/state${robotQuery(this.robotId)}`, { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error('state fetch failed')
      const value = await response.json()
      // HTTP로 다시 받는 사이 WebSocket 갱신이 왔다면 그쪽이 이미 더 새로운 상태다
      if (!this.stopped && generation === this.generation && this.controller === controller && this.current.snapshot === snapshotAtFetch) this.accept(value)
    } catch { if (!this.stopped && generation === this.generation && this.controller === controller && this.current.snapshot === snapshotAtFetch) this.fail() }
    finally { clearTimeout(timeout) }
  }
  start = () => {
    this.stopped = false
    void this.connect()
    this.watch = setInterval(() => {
      const threshold = (this.current.snapshot?.settings.browser_delay_s ?? 3) * 1000
      if (performance.now() - this.current.receivedMono >= threshold) {
        this.fail()
        if (this.socket && this.socket.readyState < WebSocket.CLOSING) this.socket.close()
      }
    }, 200)
    document.addEventListener('visibilitychange', this.refresh)
  }
  dispose = () => {
    this.stopped = true; this.generation++
    clearTimeout(this.retry); clearInterval(this.watch)
    this.controller?.abort(); this.socket?.close()
    document.removeEventListener('visibilitychange', this.refresh)
  }
}
