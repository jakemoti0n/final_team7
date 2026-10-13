import type { Command, RequestResult, Result, Stage } from './commands'
import type { ServerCommand, ServerStage, View } from './types'

// 실제 화면 제어: 서버 명령 단계 → 화면 3단계 (docs/CONTROL_API_DRAFT.md §3.1).
// 성공은 서버가 confirmed라고 한 것만. 클릭·응답만으로 성공 표시하지 않고, 자동 재전송하지 않는다.
type Shape = { stages: [Stage, Stage, Stage]; result: Result; detail: (message: string) => string }
export const stageShapes: Record<ServerStage, Shape> = {
  queued: { stages: ['running', 'waiting', 'waiting'], result: 'pending', detail: () => '서버가 요청을 받았습니다. 로봇이 가져가기를 기다립니다.' },
  delivered: { stages: ['done', 'running', 'waiting'], result: 'pending', detail: () => '로봇에 전달했습니다. 로봇 응답을 기다립니다.' },
  accepted: { stages: ['done', 'done', 'running'], result: 'pending', detail: () => '로봇이 요청을 받아들였습니다. 이후 순찰 상태 보고를 기다립니다.' },
  confirmed: { stages: ['done', 'done', 'done'], result: 'success', detail: () => '요청 이후 로봇이 보낸 순찰 상태로 확인했습니다.' },
  rejected: { stages: ['done', 'failed', 'unknown'], result: 'failed', detail: m => `로봇이 요청을 거절했습니다. 사유: ${m || '없음'}` },
  service_unavailable: { stages: ['done', 'failed', 'unknown'], result: 'failed', detail: () => '순찰 프로그램이 꺼져 있어 요청을 실행하지 않았습니다.' },
  no_response: { stages: ['done', 'unknown', 'unknown'], result: 'unknown', detail: () => '제한 시간 안에 로봇 응답이 없습니다. 자동 재전송하지 않습니다.' },
  expired: { stages: ['failed', 'unknown', 'unknown'], result: 'unknown', detail: () => '제한 시간 안에 요청이 로봇에 전달되지 않았습니다.' },
  unconfirmed: { stages: ['done', 'done', 'unknown'], result: 'unknown', detail: () => '로봇은 응답했지만 이후 상태 보고로 확인하지 못했습니다.' },
  connection_lost: { stages: ['done', 'unknown', 'unknown'], result: 'unknown', detail: () => '처리 중 연결이 끊겨 결과를 확인할 수 없습니다. 자동 재전송하지 않습니다.' },
}
export function fromServer(c: ServerCommand): RequestResult {
  const shape = stageShapes[c.stage] ?? stageShapes.connection_lost
  return { id: c.request_id, command: c.command, at: c.issued_at, stages: [...shape.stages], result: shape.result, detail: shape.detail(c.message) }
}

const postErrors: Record<string, string> = {
  command_in_progress: '처리 중인 다른 요청이 있습니다.',
  bridge_not_connected: '로봇과 연결되어 있지 않아 요청을 보내지 않았습니다.',
}
function sendFailed(command: Command, detail: string): RequestResult {
  return { id: '—', command, at: new Date().toISOString(), stages: ['failed', 'unknown', 'unknown'], result: 'failed', detail }
}

export function lockReason(view: View, request: RequestResult | null) {
  if (view.serverProblem || view.snapshot?.bridge.status !== 'connected') return '연결을 확인한 후 사용할 수 있습니다'
  if (request?.result === 'pending') return '요청을 처리하고 있습니다'
  return ''
}
/** 재개 허용은 순찰 노드의 has_resumable_task로만 판단한다 (속도로 추정하지 않음) */
export function resumeReason(view: View, lock: string) {
  if (lock) return lock
  const patrol = view.snapshot?.patrol
  if (!patrol?.state) return patrol?.update_count ? '순찰 프로그램 상태를 확인할 수 없습니다' : '순찰 상태를 확인할 수 없습니다'
  if (patrol.state === 'patrolling') return '이미 순찰 중입니다'
  return patrol.has_resumable_task ? '' : '재개할 작업이 없습니다'
}

/** 보낸 직후 서버 스냅샷이 아직 안 바뀐 동안만 화면 자체 결과(전송 중·전송 실패)를 보여 준다 */
export class LiveControl {
  private local: { result: RequestResult; base: string | null } | null = null
  constructor(private changed: () => void, private post: typeof fetch = (...a) => fetch(...a)) {}
  current(view: View): RequestResult | null {
    const server = view.snapshot?.command ?? null
    if (this.local && (server?.request_id ?? null) === this.local.base) return this.local.result
    this.local = null
    return server ? fromServer(server) : null
  }
  async send(view: View, command: Command) {
    const lock = lockReason(view, this.current(view))
    if (lock || (command === 'resume' && resumeReason(view, lock))) return
    const base = view.snapshot?.command?.request_id ?? null
    this.local = { base, result: { id: '—', command, at: new Date().toISOString(), stages: ['running', 'waiting', 'waiting'], result: 'pending', detail: '서버에 요청을 보내고 있습니다.' } }
    this.changed()
    let result: RequestResult
    try {
      const response = await this.post('/api/v1/commands', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ command }), signal: AbortSignal.timeout(5000) })
      const body = await response.json().catch(() => null)
      if (response.status === 202 && body?.request_id) result = fromServer({ message: '', updated_at: body.issued_at, ...body })
      else result = sendFailed(command, postErrors[body?.error?.code] ?? `서버가 요청을 받지 않았습니다 (${response.status}).`)
    } catch { result = sendFailed(command, '서버에 요청을 보내지 못했습니다. 자동 재전송하지 않습니다.') }
    if (this.local?.base === base) { this.local = { base, result }; this.changed() }
  }
}
