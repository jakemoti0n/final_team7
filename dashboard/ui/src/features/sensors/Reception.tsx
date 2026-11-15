import { names, topicKeys, type Snapshot } from '../../types'
import { ageText, timeText } from '../../format'
import { Badge } from '../../components/Badge'

export function Reception({ state, serverProblem, delta }: { state: Snapshot | null; serverProblem: boolean; delta: number }) {
  return <details className="card reception" data-testid="reception"><summary className="card-heading">센서 수신 상세<small>개발자용 · 토픽 4개의 수신 상태</small></summary>
    <table><thead><tr><th>항목</th><th>수신 상태</th><th>마지막 수신</th><th>수신 빈도</th></tr></thead>
      <tbody>{topicKeys.map(key => {
        const topic = state?.topics[key]
        const status = serverProblem ? 'unknown' : topic?.status ?? 'never_received'
        const hz = status === 'receiving' ? topic?.receive_hz : null
        return <tr key={key} className={status === 'delayed' ? 'delayed-row' : ''}>
          <th scope="row">{names[key]}</th><td data-label="수신 상태"><span role="status"><Badge status={status} /></span>{status === 'unknown' && <small>{topic?.received_count ? '마지막 수신 이력 보존' : '수신 기록 없음'}</small>}</td>
          <td data-label="마지막 수신"><span>{ageText(topic?.age_s ?? null, delta)}</span><small>{timeText(topic?.last_received_at ?? null)}</small></td>
          <td data-label="수신 빈도">{hz == null ? '—' : `${hz.toFixed(1)} Hz`}{status === 'receiving' && hz == null && <small>측정 중</small>}{status !== 'receiving' && topic?.last_receive_hz != null && <small>마지막 값 {topic.last_receive_hz.toFixed(1)} Hz</small>}</td>
        </tr>
      })}</tbody></table>
    <div className="table-note"><p>수신 상태는 데이터가 들어오는지만 나타냅니다. 센서의 정상 작동 여부를 판단하는 정보는 아닙니다.</p><p>수신 지연 기준 · {state ? topicKeys.map(key => `${names[key]} ${state.settings.topic_delay_s[key]}초`).join(' / ') : '설정 수신 대기'}</p></div>
  </details>
}
