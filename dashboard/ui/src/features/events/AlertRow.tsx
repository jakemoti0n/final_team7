import type { Snapshot } from '../../types'
import { timeText } from '../../format'
import { Badge } from '../../components/Badge'

export function AlertRow({ alert }: { alert: Snapshot['alerts'][number] }) {
  return <li className="alert-row" data-testid="alert-row"><time dateTime={alert.at}>{timeText(alert.at)}</time><Badge status={alert.severity}>{{ info: '정보', warning: '주의', error: '오류' }[alert.severity]}</Badge><span>{alert.message}</span>{alert.active && <small>지속 중</small>}</li>
}
