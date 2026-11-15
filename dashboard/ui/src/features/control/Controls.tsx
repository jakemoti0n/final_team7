import type { ReactNode } from 'react'
import type { MockProvider } from '../../demo'
import type { Command } from '../../commands'
import { driveControl, lockReason, stopReason, type LiveControl } from '../../control'
import type { View } from '../../types'
import { Card } from '../../components/Card'
import { ResultBox } from './ResultBox'

/** 로봇 제어 카드: 주행 시작·정지·재개 버튼 하나와 순찰 종료, 마지막 명령 결과. routesLink는 순찰 경로 페이지로 가는 링크 */
export function Controls({ demo, live, view, delta, routesLink }: { demo: MockProvider | null; live: LiveControl | null; view: View; delta: number; routesLink: ReactNode }) {
  const request = demo ? demo.machine.current : live!.current(view)
  // 주행 시작·순찰 종료도 일시정지·재개와 같은 명령 통로: 서버가 쌓고 로봇의 Bridge가 로봇 컴퓨터에서 실행한다
  const { action, reason } = driveControl(view, request)
  const stopLock = stopReason(view, lockReason(view, request))
  const pending = request?.result === 'pending'
  const stopping = pending && request?.command === 'stop'
  const launcher = view.snapshot?.launcher
  const send = (command: Command) => { if (demo) demo.request(command); else void live!.send(view, command) }
  const label = action === 'start' ? '주행 시작' : action === 'pause' ? '주행 정지' : '주행 재개'
  const busyLabel = action === 'start' ? '주행 시작 중' : action === 'pause' ? '정지 요청 중' : '재개 요청 중'
  // 노드가 0이 아닌 코드로 끝났으면 알려 준다. 로그는 로봇 컴퓨터에 있다
  const exitNote = launcher?.state === 'exited' && launcher.exit_code ? `순찰 노드가 종료 코드 ${launcher.exit_code}로 끝났습니다. 로그(로봇 컴퓨터): ${launcher.log ?? '—'}` : ''
  return <Card title="로봇 제어" className="controls">
    <div className="control-body"><p id="control-reason" role="status" className="muted">{reason || (action === 'start' ? '저장된 waypoint 경로를 로봇에 보내 새 순찰을 시작합니다.' : action === 'pause' ? '현재 순찰을 일시정지합니다.' : '멈춘 지점부터 순찰을 이어서 합니다.')}</p>
      <button data-testid="drive-command" className={`command ${action === 'pause' ? 'pause' : 'resume'}`} disabled={!!reason || pending} aria-busy={pending && request?.command !== 'stop'} aria-describedby="control-reason" onClick={() => send(action)}><span aria-hidden="true">{action === 'pause' ? '■' : '▷'}</span>{pending && request?.command !== 'stop' ? busyLabel : label}</button>
      <span data-testid="patrol-stop-wrap" title={stopLock || undefined}><button className="patrol-stop" type="button" disabled={!!stopLock} aria-busy={stopping} onClick={() => send('stop')}>{stopping ? '순찰 종료 중' : '순찰 종료'}</button></span>
      {exitNote && <p className="muted" role="status">{exitNote}</p>}
      {request && <ResultBox key={request.id} result={request} delta={delta} />}
      <p className="control-routes muted">순찰할 지점은 {routesLink}에서 확인하고 바꿉니다.</p>
    </div>
  </Card>
}
