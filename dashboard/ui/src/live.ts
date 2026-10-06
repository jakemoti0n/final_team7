import type { Provider, Snapshot, View } from './types'

export const backoff = [1000, 2000, 4000, 8000, 10000]
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
  subscribe = (fn: (view: View) => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  private emit() { this.listeners.forEach(fn => fn(this.current)) }
  private fail() { this.current = { ...this.current, serverProblem: true }; this.emit() }
  private accept(value: Snapshot) {
    if (!value?.server_run_id || !Number.isInteger(value.revision) || !value.settings || !value.topics || !value.motion || !value.bridge) throw new Error('invalid snapshot')
    const old = this.current.snapshot
    if (old?.server_run_id === value.server_run_id && value.revision <= old.revision) return
    this.current = { snapshot: value, serverProblem: false, receivedMono: performance.now() }
    this.attempt = 0
    this.emit()
  }
  private connect = () => {
    if (this.stopped) return
    const generation = this.generation
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/stream`)
    this.socket = ws
    ws.onmessage = event => {
      if (this.stopped || generation !== this.generation || this.socket !== ws) return
      try { this.accept(JSON.parse(event.data)) } catch { this.fail(); ws.close() }
    }
    ws.onerror = () => { if (!this.stopped && this.socket === ws) { this.fail(); ws.close() } }
    ws.onclose = () => {
      if (this.stopped || generation !== this.generation || this.socket !== ws) return
      this.fail()
      this.retry = setTimeout(this.connect, backoff[Math.min(this.attempt++, backoff.length - 1)])
    }
  }
  private refresh = async () => {
    if (document.visibilityState !== 'visible' || this.stopped) return
    this.fail() // Returning to a tab never certifies an old snapshot as current.
    this.controller?.abort()
    const controller = new AbortController()
    this.controller = controller
    const generation = this.generation
    const snapshotAtFetch = this.current.snapshot
    const timeout = setTimeout(() => controller.abort(), 3000)
    try {
      const response = await fetch('/api/v1/state', { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error('state fetch failed')
      const value = await response.json()
      // A WebSocket update arriving during HTTP refresh already supplies newer state.
      if (!this.stopped && generation === this.generation && this.controller === controller && this.current.snapshot === snapshotAtFetch) this.accept(value)
    } catch { if (!this.stopped && generation === this.generation && this.controller === controller && this.current.snapshot === snapshotAtFetch) this.fail() }
    finally { clearTimeout(timeout) }
  }
  start = () => {
    this.stopped = false
    this.connect()
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
