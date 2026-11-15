import { useState } from 'react'
import { resultLabels, type RequestResult } from '../../commands'
import { ageText, timeText } from '../../format'
import { Badge } from '../../components/Badge'

/** 요청 후 경과 초. 서버 명령은 서버가 잰 값 + 받은 뒤 지난 시간, 화면 자체 결과는 브라우저 시계 */
function requestAge(result: RequestResult, delta: number) {
  return result.age_s != null ? result.age_s + delta : Math.max(0, (Date.now() - Date.parse(result.at)) / 1000)
}
const FOLD_AFTER_S = 60
export function ResultBox({ result, delta }: { result: RequestResult; delta: number }) {
  const stageLabels = { waiting: '대기', running: '진행 중', done: '완료', failed: '실패', unknown: '확인 불가' }
  const age = requestAge(result, delta)
  const [open, setOpen] = useState(false)
  if (result.result !== 'pending' && age >= FOLD_AFTER_S && !open) return <div className="result folded" role="status" data-testid="command-result">
    <Badge status={result.result}>{resultLabels[result.command][result.result]}</Badge><span>{ageText(age)}</span><button className="link" onClick={() => setOpen(true)}>자세히</button></div>
  return <div className="result" role="status" data-testid="command-result" aria-busy={result.result === 'pending'}>
    <Badge status={result.result}>{resultLabels[result.command][result.result]}</Badge>
    <p>{result.detail}</p>
    <ol className="steps" data-testid="command-steps">{['요청 전송', '로봇 응답', '상태 확인'].map((label, i) => <li key={label}>{label}<strong>{stageLabels[result.stages[i]]}</strong></li>)}</ol>
    <small>요청 시각 {timeText(result.at)} · {ageText(age)}</small>{result.id !== '—' && <small className="request-id">요청 ID {result.id}</small>}
  </div>
}
