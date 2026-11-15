import type { ReactNode } from 'react'
import { labels, type Tone } from '../status'

export function Badge({ status, tone: forced, children }: { status: string; tone?: Tone; children?: ReactNode }) {
  const tone = forced ?? (['connected', 'receiving', 'moving', 'success', 'done'].includes(status) ? 'good' : ['delayed', 'warning'].includes(status) ? 'warn' : ['disconnected', 'failed', 'error'].includes(status) ? 'bad' : 'neutral')
  return <span className={`badge ${tone}`}><span aria-hidden="true">{tone === 'good' ? '●' : tone === 'warn' || tone === 'bad' ? '!' : '○'}</span>{children ?? labels[status]}</span>
}
