import type { Command, RequestResult, Result, Stage } from './commands'
import type { ServerCommand, ServerStage, View } from './types'
import { api } from './auth'

// 실제 화면 제어: 서버 명령 단계 → 화면 3단계 (docs/CONTROL_API_DRAFT.md §3.1).
// 성공은 서버가 confirmed라고 한 것만. 클릭·응답만으로 성공 표시하지 않고, 자동 재전송하지 않는다.
// 주행 시작·순찰 종료도 같은 명령 통로로 Bridge가 로봇 컴퓨터에서 실행한다 (§2.5)
type Shape = { stages: [Stage, Stage, Stage]; result: Result; detail: (message: string, command: Command) => string }
const launch = (command: Command) => command === 'start' || command === 'stop'
export const stageShapes: Record<ServerStage, Shape> = {
  queued: { stages: ['running', 'waiting', 'waiting'], result: 'pending', detail: () => '서버가 요청을 받았습니다. 로봇이 가져가기를 기다립니다.' },
  delivered: { stages: ['done', 'running', 'waiting'], result: 'pending', detail: () => '로봇에 전달했습니다. 로봇 응답을 기다립니다.' },
  accepted: { stages: ['done', 'done', 'running'], result: 'pending', detail: (_, c) => c === 'start' ? '로봇이 순찰 노드를 실행했습니다. 순찰 상태 보고를 기다립니다.' : c === 'stop' ? '로봇이 순찰 노드에 종료 신호를 보냈습니다. 진행 중인 이동을 취소하고 끝나기를 기다립니다.' : '로봇이 요청을 받아들였습니다. 이후 순찰 상태 보고를 기다립니다.' },
  confirmed: { stages: ['done', 'done', 'done'], result: 'success', detail: (_, c) => c === 'stop' ? '순찰 노드가 종료된 것을 로봇 보고로 확인했습니다.' : '요청 이후 로봇이 보낸 순찰 상태로 확인했습니다.' },
  rejected: { stages: ['done', 'failed', 'unknown'], result: 'failed', detail: (m, c) => `${launch(c) ? '로봇이 실행하지 못했습니다' : '로봇이 요청을 거절했습니다'}. 사유: ${m || '없음'}` },
  service_unavailable: { stages: ['done', 'failed', 'unknown'], result: 'failed', detail: () => '순찰 프로그램이 꺼져 있어 요청을 실행하지 않았습니다.' },
  no_response: { stages: ['done', 'unknown', 'unknown'], result: 'unknown', detail: () => '제한 시간 안에 로봇 응답이 없습니다. 자동 재전송하지 않습니다.' },
  // Bridge가 실행 직전 서버에 확인(claim)하므로 expired는 "실행 안 함"이 확실하다 (CHANGELOG (28))
  expired: { stages: ['failed', 'unknown', 'unknown'], result: 'failed', detail: () => '로봇에 제때 전달되지 않아 실행하지 않았습니다. 필요하면 다시 눌러 주세요.' },
  unconfirmed: { stages: ['done', 'done', 'unknown'], result: 'unknown', detail: () => '로봇은 응답했지만 이후 상태 보고로 확인하지 못했습니다.' },
  connection_lost: { stages: ['done', 'unknown', 'unknown'], result: 'unknown', detail: () => '처리 중 연결이 끊겨 결과를 확인할 수 없습니다. 자동 재전송하지 않습니다.' },
}
export function fromServer(c: ServerCommand): RequestResult {
  const shape = stageShapes[c.stage] ?? stageShapes.connection_lost
  return { id: c.request_id, command: c.command, at: c.issued_at, age_s: c.age_s ?? null, stages: [...shape.stages], result: shape.result, detail: shape.detail(c.message, c.command) }
}

const postErrors: Record<string, string> = {
  command_in_progress: '처리 중인 다른 요청이 있습니다.',
  bridge_not_connected: '로봇과 연결되어 있지 않아 요청을 보내지 않았습니다.',
  unknown_robot: '서버가 이 로봇의 상태를 받은 적이 없습니다. 로봇을 다시 선택해 주세요.',
  bridge_unsupported: '로봇의 Bridge가 주행 시작·순찰 종료를 지원하지 않습니다. relay_prog를 업데이트해 주세요.',
  patrol_already_running: '이미 순찰 노드가 실행 중입니다.',
  patrol_not_running: '로봇의 Bridge가 띄운 순찰 노드가 실행 중이지 않습니다.',
  invalid_route: '저장된 waypoint 경로가 올바르지 않습니다. 마지막 지점이 정지 지점인지 확인해 주세요.',
  waypoints_unavailable: '서버가 waypoint 파일을 읽지 못했습니다.',
  waypoints_not_configured: '서버에 waypoint 파일이 설정되지 않았습니다.',
  login_required: '로그인이 끝나 요청을 보내지 않았습니다. 다시 로그인해 주세요.',
  password_change_required: '비밀번호를 바꾼 뒤 사용할 수 있습니다.',
  cross_site_request: '다른 사이트에서 보낸 요청이라 서버가 거절했습니다.',
}
function sendFailed(command: Command, detail: string): RequestResult {
  return { id: '—', command, at: new Date().toISOString(), stages: ['failed', 'unknown', 'unknown'], result: 'failed', detail }
}

export function lockReason(view: View, request: RequestResult | null) {
  if (view.serverProblem || view.snapshot?.bridge.status !== 'connected') return '연결을 확인한 후 사용할 수 있습니다'
  if (request?.result === 'pending') return '요청을 처리하고 있습니다'
  return ''
}
/** 이미 멈췄다고 순찰 노드가 알려 준 경우만 잠근다. 모르면 누를 수 있게 둔다 (멈추는 쪽은 막지 않음) */
export function pauseReason(view: View, lock: string) {
  if (lock) return lock
  const state = view.snapshot?.patrol?.state
  return state === 'paused' || state === 'pausing' ? '이미 일시정지 상태입니다' : ''
}
/** 재개 허용은 순찰 노드의 has_resumable_task로만 판단한다 (속도로 추정하지 않음) */
export function resumeReason(view: View, lock: string) {
  if (lock) return lock
  const patrol = view.snapshot?.patrol
  if (!patrol?.state) return patrol?.update_count ? '순찰 프로그램 상태를 확인할 수 없습니다' : '순찰 상태를 확인할 수 없습니다'
  if (patrol.state === 'patrolling') return '이미 순찰 중입니다'
  return patrol.has_resumable_task ? '' : '재개할 작업이 없습니다'
}
const unsupported = '로봇의 Bridge를 업데이트해야 사용할 수 있습니다'
/** 시작: 새 Bridge(launcher 보고)이고, 서버가 순찰 노드가 돈다고 보지 않을 때만 */
export function startReason(view: View, lock: string) {
  if (lock) return lock
  const launcher = view.snapshot?.launcher
  if (!launcher?.commands.includes('start')) return unsupported
  return view.snapshot?.patrol_running ? '이미 순찰 노드가 실행 중입니다' : ''
}
/** 종료: Bridge가 띄운 노드만 끌 수 있다 (다른 터미널에서 띄운 노드는 대상 아님) */
export function stopReason(view: View, lock: string) {
  if (lock) return lock
  const launcher = view.snapshot?.launcher
  if (!launcher?.commands.includes('stop')) return unsupported
  if (launcher.state === 'running') return ''
  return launcher.other_patrol_running ? '다른 곳에서 띄운 순찰 노드는 여기서 끌 수 없습니다' : '실행 중인 순찰 노드가 없습니다'
}
export function commandReason(view: View, command: Command, lock: string) {
  return { pause: pauseReason, resume: resumeReason, start: startReason, stop: stopReason }[command](view, lock)
}

/** 보낸 직후 서버 스냅샷이 아직 안 바뀐 동안만 화면 자체 결과(전송 중·전송 실패)를 보여 준다 */
export class LiveControl {
  private local: { result: RequestResult; base: string | null } | null = null
  /** robotId: 명령을 보낼 로봇. 비우면 서버의 기본 로봇 */
  constructor(private changed: () => void, private post: typeof fetch = (...a) => api(...a), private robotId = '') {}
  current(view: View): RequestResult | null {
    const server = view.snapshot?.command ?? null
    if (this.local && (server?.request_id ?? null) === this.local.base) return this.local.result
    this.local = null
    return server ? fromServer(server) : null
  }
  async send(view: View, command: Command) {
    if (commandReason(view, command, lockReason(view, this.current(view)))) return
    const base = view.snapshot?.command?.request_id ?? null
    this.local = { base, result: { id: '—', command, at: new Date().toISOString(), stages: ['running', 'waiting', 'waiting'], result: 'pending', detail: '서버에 요청을 보내고 있습니다.' } }
    this.changed()
    let result: RequestResult
    try {
      const response = await this.post('/api/v1/commands', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(this.robotId ? { command, robot_id: this.robotId } : { command }), signal: AbortSignal.timeout(5000) })
      const body = await response.json().catch(() => null)
      if (response.status === 202 && body?.request_id) result = fromServer({ message: '', updated_at: body.issued_at, ...body })
      else result = sendFailed(command, postErrors[body?.error?.code] ?? `서버가 요청을 받지 않았습니다 (${response.status}).`)
    } catch { result = sendFailed(command, '서버에 요청을 보내지 못했습니다. 자동 재전송하지 않습니다.') }
    if (this.local?.base === base) { this.local = { base, result }; this.changed() }
  }
}

export type DriveAction = 'start' | 'pause' | 'resume'
/** A single control follows the patrol state reported by the Bridge. */
export function driveControl(view: View, request: RequestResult | null): { action: DriveAction; reason: string } {
  const lock = lockReason(view, request)
  // 시작 요청 중에는 "주행 시작 중"으로 둔다. Bridge가 띄운 노드가 끝났으면 남은 순찰 상태는 오래된 것
  if (request?.result === 'pending' && request.command === 'start') return { action: 'start', reason: lock }
  const launcher = view.snapshot?.launcher
  if (launcher?.state === 'exited' && !view.snapshot?.patrol_running) return { action: 'start', reason: startReason(view, lock) }
  const patrol = view.snapshot?.patrol
  if (patrol?.state === 'paused') return { action: 'resume', reason: resumeReason(view, lock) }
  if (patrol?.state === 'patrolling') return { action: 'pause', reason: pauseReason(view, lock) }
  if (patrol?.state === 'waiting_localization' || patrol?.state === 'pausing')
    return { action: 'pause', reason: lock || (patrol.state === 'pausing' ? '정지 요청을 처리하고 있습니다' : '위치 확인 중에는 정지할 수 없습니다') }
  if (!patrol) return { action: 'start', reason: lock || '순찰 상태를 확인할 수 없습니다' }
  return { action: 'start', reason: startReason(view, lock) }
}

/** 화면 전체에서 waypoint 편집을 잠글지. 서버 판단(patrol_running)이 있으면 그것을, 없으면 순찰 상태로 */
export function waypointLocked(view: View, request: RequestResult | null) {
  if (request?.result === 'pending' && launch(request.command)) return true
  const snapshot = view.snapshot
  if (snapshot?.patrol_running !== undefined) return snapshot.patrol_running
  return ['waiting_localization', 'patrolling', 'pausing', 'paused'].includes(snapshot?.patrol?.state ?? '')
}
