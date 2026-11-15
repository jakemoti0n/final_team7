import { useState } from 'react'
import { scenarios, type BridgeVersion, type MockProvider, type Patrol, type Scenario } from '../../demo'
import { commandNames, type Command, type Outcome } from '../../commands'

export function DemoTools({ demo }: { demo: MockProvider }) {
  const [, redraw] = useState(0)
  const outcomes: Record<Outcome, string> = { success: '성공', reject: '명시적 거절', no_response: '응답 없음', no_confirmation: '응답 후 상태 확인 없음', late: '제한 시간 후 늦은 결과' }
  return <aside className="demo-tools" aria-label="데모 시나리오 도구"><div className="container tools-inner">
    <div><strong>데모 시나리오 도구</strong><small>시나리오 변경·초기화 시 진행 요청과 결과가 지워집니다.</small></div>
    <label>화면 상태<select aria-label="화면 상태" value={demo.scenario} onChange={e => demo.reset(e.target.value as Scenario)}>{Object.entries(scenarios).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label>Bridge 버전<select aria-label="Bridge 버전" value={demo.bridgeVersion} onChange={e => demo.setBridgeVersion(e.target.value as BridgeVersion)}><option value="current">현재 (주행 시작·순찰 종료 지원)</option><option value="legacy">이전 버전 (시작·종료 미지원)</option></select></label>
    <label>가상 순찰 상태<select aria-label="가상 순찰 상태" value={demo.patrol} onChange={e => demo.setPatrol(e.target.value as Patrol)}><option value="paused">일시 중단 · 재개할 작업 있음</option><option value="patrolling">이미 순찰 중</option><option value="empty">재개할 작업 없음</option><option value="unknown">상태 미확인</option></select></label>
    {(Object.keys(commandNames) as Command[]).map(command => <label key={command}>{commandNames[command]} 결과<select aria-label={`${commandNames[command]} 결과`} value={demo.outcomes[command]} onChange={e => { demo.outcomes[command] = e.target.value as Outcome; redraw(n => n + 1) }}>{Object.entries(outcomes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>)}
    <label>응답 제한 시간(초)<input aria-label="응답 제한 시간(초)" type="number" min="0.1" max="60" step="0.1" defaultValue="5" onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= .1 && n <= 60) demo.machine.responseTimeout = n * 1000 }} /></label>
    <label>상태 확인 제한 시간(초)<input aria-label="상태 확인 제한 시간(초)" type="number" min="0.1" max="60" step="0.1" defaultValue="5" onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= .1 && n <= 60) demo.machine.confirmationTimeout = n * 1000 }} /></label>
    <button onClick={() => demo.reset()}>시나리오 초기화</button><button onClick={() => demo.disconnect()}>진행 중 연결 끊기</button>
  </div></aside>
}
