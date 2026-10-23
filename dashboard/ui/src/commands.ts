export type Command = 'pause' | 'resume' | 'follow_start' | 'follow_stop' | 'follow_enroll'
/** 순찰 명령(가상 데모가 흉내 내는 것). 따라가기 명령은 실제 화면에만 있다 (PROJECT.md 2-9 3단계) */
export const patrolCommands = ['pause', 'resume'] as const
export const followCommands = ['follow_enroll', 'follow_start', 'follow_stop'] as const
export type Outcome = 'success' | 'reject' | 'no_response' | 'no_confirmation' | 'late'
export type Stage = 'waiting' | 'running' | 'done' | 'failed' | 'unknown'
export type Result = 'pending' | 'success' | 'failed' | 'unknown'
export interface RequestResult { id: string; command: Command; at: string; age_s?: number | null; stages: [Stage, Stage, Stage]; result: Result; detail: string }
export const commandNames: Record<Command, string> = { pause: '일시정지', resume: '순찰 재개', follow_start: '따라가기 시작', follow_stop: '따라가기 정지', follow_enroll: '운용자 등록' }
export const resultLabels: Record<Command, Record<Result, string>> = {
  pause: { pending: '정지 요청 중', success: '정지 상태 확인됨', failed: '정지 요청 실패', unknown: '정지 여부 확인 불가' },
  resume: { pending: '재개 요청 중', success: '재개 확인됨', failed: '재개 실패', unknown: '재개 여부 확인 불가' },
  follow_start: { pending: '따라가기 시작 요청 중', success: '따라가기 시작 확인됨', failed: '따라가기 시작 실패', unknown: '따라가기 시작 여부 확인 불가' },
  follow_stop: { pending: '따라가기 정지 요청 중', success: '따라가기 정지 확인됨', failed: '따라가기 정지 실패', unknown: '따라가기 정지 여부 확인 불가' },
  follow_enroll: { pending: '운용자 등록 요청 중', success: '운용자 등록 확인됨', failed: '운용자 등록 실패', unknown: '운용자 등록 여부 확인 불가' },
}

/** Only correlated explicit mock events can finish a request. Telemetry never enters this machine. */
export class CommandMachine {
  current: RequestResult | null = null
  responseTimeout = 5000
  confirmationTimeout = 5000
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private responseTimer?: ReturnType<typeof setTimeout>
  private confirmationTimer?: ReturnType<typeof setTimeout>
  constructor(private changed: () => void, private finished: (r: RequestResult) => void) {}
  private later(fn: () => void, ms: number) {
    const timer = setTimeout(() => { this.timers.delete(timer); fn() }, ms)
    this.timers.add(timer)
    return timer
  }
  start(command: Command, outcome: Outcome): string | null {
    if (this.current?.result === 'pending') return null
    this.cancelTimers()
    const id = crypto.randomUUID()
    this.current = { id, command, at: new Date().toISOString(), stages: ['running', 'waiting', 'waiting'], result: 'pending', detail: '가상 요청을 전송하고 있습니다.' }
    this.changed()
    this.later(() => {
      if (!this.matches(id)) return
      this.current!.stages = ['done', 'running', 'waiting']
      this.current!.detail = '전송 완료. 로봇 응답을 기다립니다.'
      this.changed()
      this.responseTimer = this.later(() => this.finish(id, 'unknown', 1, '제한 시간 안에 로봇 응답이 없습니다.'), this.responseTimeout)
      if (outcome !== 'no_response') this.later(() => {
        this.event(id, outcome === 'reject' ? 'rejected' : 'response')
        if (outcome === 'success' || outcome === 'late') this.later(() => this.event(id, 'confirmed'), 1000)
      }, outcome === 'late' ? this.responseTimeout + 500 : 500)
    }, 100)
    return id
  }
  private matches(id: string) { return this.current?.id === id && this.current.result === 'pending' }
  event(id: string, event: 'response' | 'rejected' | 'confirmed') {
    if (!this.matches(id)) return
    const r = this.current!
    if ((event === 'response' || event === 'rejected') && r.stages[1] === 'running') {
      clearTimeout(this.responseTimer)
      if (event === 'rejected') { this.finish(id, 'failed', 1, '가상 로봇이 요청을 명시적으로 거절했습니다.'); return }
      r.stages = ['done', 'done', 'running']
      r.detail = '로봇 응답 수신. 요청 ID에 대응하는 상태 확인을 기다립니다.'
      this.changed()
      this.confirmationTimer = this.later(() => this.finish(id, 'unknown', 2, '로봇은 응답했지만 이후 상태 보고가 없습니다.'), this.confirmationTimeout)
    } else if (event === 'confirmed' && r.stages[2] === 'running') {
      clearTimeout(this.confirmationTimer)
      this.finish(id, 'success', 2, '같은 요청 ID의 가상 상태 보고를 확인했습니다. 실제 로봇의 검증 결과가 아닙니다.')
    }
  }
  private finish(id: string, result: Exclude<Result, 'pending'>, stage: number, detail: string) {
    if (!this.matches(id)) return
    const r = this.current!
    r.result = result; r.detail = detail
    r.stages[stage] = result === 'success' ? 'done' : result === 'failed' ? 'failed' : 'unknown'
    for (let next = stage + 1; next < 3; next++) r.stages[next] = 'unknown'
    this.changed(); this.finished({ ...r, stages: [...r.stages] })
  }
  disconnect() {
    if (this.current?.result === 'pending') this.finish(this.current.id, 'unknown', this.current.stages.indexOf('running'), '연결이 끊겨 처리 결과를 확인할 수 없습니다. 자동 재전송하지 않습니다.')
  }
  private cancelTimers() { this.timers.forEach(clearTimeout); this.timers.clear() }
  reset() { this.cancelTimers(); this.current = null; this.changed() }
  dispose() { this.cancelTimers() }
}
