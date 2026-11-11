import { CommandMachine, resultLabels, type Command, type Outcome, type RequestResult } from './commands'
import { commandReason, lockReason } from './control'
import { topicKeys, type Snapshot, type Provider, type View, type Alert, type Launcher, type PatrolInfo, type PoseInfo } from './types'
import type { MapInfo, Waypoint } from './map'

export type Scenario = 'normal' | 'partial' | 'delayed' | 'disconnected' | 'initial' | 'server'
export const scenarios: Record<Scenario, string> = { normal: '정상 수신', partial: '일부 토픽 지연', delayed: '로봇 상태 수신 지연', disconnected: '로봇 연결 끊김', initial: '최초 접속', server: '서버 연결 문제' }
export type Patrol = 'paused' | 'patrolling' | 'empty' | 'unknown'
/** 연결된 Bridge: current는 주행 시작·순찰 종료 지원(v3), legacy는 이전 Bridge(v2, 시작·종료 버튼 잠김) */
export type BridgeVersion = 'current' | 'legacy'
// 데모 지도: 그림 없이 순찰 지점만 (값은 test_waypoints.yaml과 같은 배치). 서버를 부르지 않는다
export const demoMap: MapInfo = { resolution: .05, origin: [-7.546, -7.524, 0], width: 302, height: 302, image: null, waypoints: [
  ['A', 'pass', 5.3, 5.39], ['B', 'pass', .42, 5.25], ['C', 'stop', -1.72, 2.03], ['D', 'pass', -5.32, 5.56], ['E', 'pass', -5.52, -1.84],
  ['F', 'pass', -.15, -2.28], ['G', 'stop', -.07, -6.04], ['H', 'pass', 6.01, -6.04], ['I', 'pass', 6.64, .1], ['J', 'stop', .83, -.01],
].map(([name, type, x, y]) => ({ name, type, x, y }) as MapInfo['waypoints'][number]) }
const settings: Snapshot['settings'] = { robot_id: 'LIMBO-01', bridge_delay_s: 3, bridge_disconnect_s: 10, browser_delay_s: 3, topic_delay_s: { odom: 3, lidar_raw: 3, lidar_filtered: 3, camera_raw: 3 }, linear_threshold_mps: .05, angular_threshold_radps: .05, alert_limit: 100 }
export class MockProvider implements Provider {
  current: View = { snapshot: null, serverProblem: false, receivedMono: performance.now() }
  scenario: Scenario = 'normal'
  patrol: Patrol = 'patrolling'
  outcomes: Record<Command, Outcome> = { pause: 'success', resume: 'success', start: 'success', stop: 'success' }
  bridgeVersion: BridgeVersion = 'current'
  // 가상 Bridge가 띄운 순찰 노드. 실제처럼 시작·종료 명령이 확인돼야 바뀐다
  launched: Launcher['state'] = 'running'
  private pid = 4242
  waypoints: Waypoint[] = demoMap.waypoints.map(w => ({ ...w }))
  private target = 2
  private x = -.2
  private y = 3.6
  private yaw = 2.3
  machine: CommandMachine
  private alerts: Alert[] = []
  private listeners = new Set<(v: View) => void>()
  private timer?: ReturnType<typeof setInterval>
  private revision = 0
  private run = crypto.randomUUID()
  private scenarioAt = new Date().toISOString()
  constructor() { this.machine = new CommandMachine(() => this.update(), result => this.finish(result)) }
  subscribe = (fn: (view: View) => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  start = () => { this.update(); this.timer = setInterval(() => this.update(), 1000) }
  dispose = () => { clearInterval(this.timer); this.machine.dispose() }
  reset(scenario: Scenario = this.scenario) {
    this.scenario = scenario; this.patrol = 'patrolling'; this.launched = 'running'; this.alerts = []; this.run = crypto.randomUUID(); this.scenarioAt = new Date().toISOString()
    this.machine.reset()
    if (scenario === 'partial') this.alerts.push(this.alert('LiDAR 필터 결과 수신 지연', 'warning', true))
    if (scenario === 'delayed' || scenario === 'disconnected') this.alerts.push(this.alert(scenarios[scenario], scenario === 'delayed' ? 'warning' : 'error', true))
    this.update()
  }
  // 처리 중 연결 끊김을 시험하려고 진행 중인 요청을 그대로 둔다
  disconnect() { this.scenario = 'disconnected'; this.scenarioAt = new Date().toISOString(); this.machine.disconnect(); this.update() }
  setPatrol(value: Patrol) {
    this.patrol = value
    if (value === 'paused' || value === 'patrolling') this.launched = 'running'
    if (value === 'empty') this.launched = 'exited'
    this.update()
  }
  setBridgeVersion(value: BridgeVersion) { this.bridgeVersion = value; this.update() }
  setWaypoints(waypoints: Waypoint[]) {
    const targetName = this.waypoints[this.target]?.name
    this.waypoints = waypoints.map(w => ({ ...w }))
    const matching = this.waypoints.findIndex(w => w.name === targetName)
    this.target = matching >= 0 ? matching : this.waypoints.length ? Math.min(this.target, this.waypoints.length - 1) : 0
    if (!this.waypoints.length) this.patrol = 'empty'
    this.update()
  }
  private alert(message: string, severity: Alert['severity'], active = false): Alert {
    return { id: crypto.randomUUID(), key: 'demo', at: new Date().toISOString(), severity, message: `데모 · ${message}`, kind: active ? 'problem' : 'control', active }
  }
  private finish(r: RequestResult) {
    if (r.result === 'success') {
      if (r.command === 'pause') this.patrol = 'paused'
      if (r.command === 'resume') this.patrol = 'patrolling'
      if (r.command === 'start') { this.target = 0; this.patrol = 'patrolling'; this.launched = 'running'; this.pid++ }
      if (r.command === 'stop') { this.patrol = 'unknown'; this.launched = 'exited' }   // 발행자 사라짐 → 상태 비움
    }
    this.alerts = [this.alert(resultLabels[r.command][r.result], r.result === 'failed' ? 'error' : r.result === 'unknown' ? 'warning' : 'info'), ...this.alerts].slice(0, 100)
    this.update()
  }
  /** 실제 화면과 같은 잠금 규칙(control.ts)을 가상 스냅샷에 적용한다 */
  request(command: Command) {
    if (commandReason(this.current, command, lockReason(this.current, this.machine.current))) return
    this.machine.start(command, this.outcomes[command])
  }
  private launcher(): Launcher | null {
    if (this.bridgeVersion === 'legacy') return null
    const idle = this.launched === 'idle'
    return { commands: ['pause', 'resume', 'start', 'stop'], state: this.launched, pid: idle ? null : this.pid, exit_code: this.launched === 'exited' ? 0 : null,
      waypoints_revision: idle ? null : '0'.repeat(64), log: idle ? null : '/tmp/limbo-patrol-demo.log', other_patrol_running: false }
  }
  // 순찰 중이면 1초에 0.5 m씩 다음 지점으로 (끝까지 가면 처음부터)
  private move() {
    if (this.patrol !== 'patrolling' || !this.waypoints.length) return
    const w = this.waypoints[this.target], dx = w.x - this.x, dy = w.y - this.y, d = Math.hypot(dx, dy)
    this.yaw = Math.atan2(dy, dx)
    if (d <= .5) { this.x = w.x; this.y = w.y; this.target = (this.target + 1) % this.waypoints.length }
    else { this.x += dx / d * .5; this.y += dy / d * .5 }
  }
  private patrolInfo(at: string, age: number): PatrolInfo | null {
    // 실제 Bridge처럼: 순찰 노드가 끝나면 받은 기록은 남기고 상태 내용만 비운다 (순찰 상태 확인 불가)
    if (this.patrol === 'unknown' && this.launched === 'exited') return { state: null, waypoint_index: null, waypoint_count: null, waypoint_name: null, has_resumable_task: null, reason: null, update_count: this.revision, last_received_at: at, age_s: age } as unknown as PatrolInfo
    if (this.patrol === 'unknown') return null
    const w = this.waypoints, done = this.patrol === 'empty' || !w.length
    return { state: done ? 'completed' : this.patrol as 'paused' | 'patrolling', waypoint_index: done ? w.length : this.target, waypoint_count: w.length, waypoint_name: done ? '' : w[this.target].name,
      has_resumable_task: this.patrol === 'paused', reason: done ? 'mission completed' : '', update_count: this.revision, last_received_at: at, age_s: age }
  }
  private poseInfo(at: string | null, age: number | null, stale: boolean): PoseInfo {
    return at ? { frame_id: 'map', x: this.x, y: this.y, yaw: this.yaw, position_std_m: .08, last_received_at: at, age_s: age, stale }
      : { frame_id: null, x: null, y: null, yaw: null, position_std_m: null, last_received_at: null, age_s: null, stale: true }
  }
  private update() {
    const initial = this.scenario === 'initial'
    const uncertain = this.scenario === 'delayed' || this.scenario === 'disconnected'
    const now = new Date().toISOString()
    const at = uncertain ? this.scenarioAt : now
    const age = uncertain ? (this.scenario === 'delayed' ? 4 : 12) : .1
    if (!initial && !uncertain) this.move()
    const motion = { linear_speed_mps: .25, angular_velocity_radps: 0, last_received_at: at, age_ms: age * 1000, age_s: age }
    const snapshot: Snapshot = {
      server_run_id: this.run, revision: ++this.revision, server_utc: now, robot_id: 'LIMBO-01', settings,
      bridge: { status: initial ? 'checking' : uncertain ? this.scenario as 'delayed' | 'disconnected' : 'connected', last_received_at: initial ? null : at, age_s: initial ? null : age, session_id: this.run, sequence: this.revision },
      topics: Object.fromEntries(topicKeys.map(key => {
        const delayed = this.scenario === 'partial' && key === 'lidar_filtered'
        return [key, { status: initial ? 'never_received' : uncertain ? 'unknown' : delayed ? 'delayed' : 'receiving', last_received_at: initial ? null : delayed ? this.scenarioAt : at, age_s: initial ? null : delayed ? 6 : age, received_count: initial ? 0 : 40, receive_hz: initial || uncertain || delayed ? null : 10, last_receive_hz: initial ? null : 10 }]
      })) as Snapshot['topics'],
      motion: { status: initial ? 'unconfirmed' : uncertain ? 'unknown' : 'moving', rotating: false, current: initial || uncertain ? null : motion, age_s: initial ? null : age, last_valid: initial ? null : motion }, alerts: [...this.alerts],
      patrol: initial ? null : this.patrolInfo(at, age), pose: this.poseInfo(initial ? null : at, initial ? null : age, uncertain), command: null, map_available: true,
      launcher: initial ? null : this.launcher(),
      patrol_running: this.bridgeVersion === 'legacy' ? this.patrol === 'paused' || this.patrol === 'patrolling' : this.launched === 'running',
    }
    this.current = { snapshot, serverProblem: this.scenario === 'server', receivedMono: performance.now() }
    this.listeners.forEach(fn => fn(this.current))
  }
}
