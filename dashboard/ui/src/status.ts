import { names, topicKeys, type View } from './types'

/** 상태 값 → 화면 문구와 톤(good·warn·bad·neutral). 색만이 아니라 문구·기호로도 구분한다 */
export const labels: Record<string, string> = { checking: '연결 확인 중', connected: '연결됨', delayed: '수신 지연', disconnected: '연결 끊김', never_received: '미수신', receiving: '수신 중', unknown: '현재 확인 불가', unconfirmed: '확인 전', moving: '이동 중', stopped: '정지 상태' }
export type Tone = 'good' | 'warn' | 'bad' | 'neutral'
export const patrolLabels: Record<string, string> = { waiting_localization: '위치 확인 중', patrolling: '순찰 중', pausing: '멈추는 중', paused: '일시정지', completed: '순찰 완료', failed: '순찰 실패' }
export const patrolTones: Record<string, Tone> = { patrolling: 'good', pausing: 'warn', paused: 'warn', failed: 'bad' }
/** 순찰 노드가 이동 실패를 사유로 알린 경우 (상태는 그대로 patrolling·paused, docs/CONTROL_SCREEN.md A 4단계 A안) */
export function patrolLabel(state: string, reason: string): { label: string; tone: Tone; note: string } {
  const retry = /^navigation failed, retry (\d+\/\d+)$/.exec(reason)
  if (state === 'patrolling' && retry) return { label: `순찰 중 · 이동 다시 시도 (${retry[1]})`, tone: 'warn', note: '이동이 막혀 잠시 뒤 다시 갑니다.' }
  if (state === 'paused' && reason === 'navigation failed') return { label: '이동 실패 · 확인 후 재개', tone: 'warn', note: '여러 번 다시 가 봐도 막혀서 멈췄습니다. 주변을 확인한 뒤 재개를 눌러 주세요.' }
  return { label: patrolLabels[state] ?? state, tone: patrolTones[state] ?? 'neutral', note: '' }
}
/** 상태 한 줄 요약 (docs/CONTROL_SCREEN.md D): 정상 / 확인 필요 / 연결 끊김 */
export function overall(view: View): { tone: Tone; label: string; detail: string } {
  const state = view.snapshot
  if (view.serverProblem) return { tone: 'bad', label: '연결 끊김', detail: '서버 상태를 갱신할 수 없음' }
  const bridge = state?.bridge.status ?? 'checking'
  if (bridge === 'disconnected') return { tone: 'bad', label: '연결 끊김', detail: '로봇과 연결 끊김' }
  if (bridge === 'checking') return { tone: 'warn', label: '확인 필요', detail: '로봇 연결 확인 중' }
  if (bridge === 'delayed') return { tone: 'warn', label: '확인 필요', detail: '로봇 상태 수신 지연' }
  const late = topicKeys.filter(key => state!.topics[key].status !== 'receiving')
  if (late.length) return { tone: 'warn', label: '확인 필요', detail: late.map(key => `${names[key]} ${state!.topics[key].status === 'never_received' ? '미수신' : '수신 지연'}`).join(', ') }
  return { tone: 'good', label: '정상', detail: '' }
}
