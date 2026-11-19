import { useEffect, useState } from 'react'
import { demoVisitorGuide, demoVisitorState, parseVisitorGuide, parseVisitorState, type VisitorGuide, type VisitorState } from './visitor'

export const VISITOR_POLL_MS = 3000
const TIMEOUT_MS = 5000

export interface VisitorData {
  state: VisitorState | null    // 마지막으로 받은 상태 (받지 못하게 되어도 남겨 두고 오래됨으로 표시)
  receivedAt: number | null     // 받은 시각 (performance.now)
  problem: boolean              // 마지막 요청이 실패했거나 응답 모양이 이상함
  closed: boolean               // 서버가 방문자 화면을 껐다 (404)
  guide: VisitorGuide | null    // 안내 약도 (없으면 자동 약도가 메인)
  now: number                   // 1초마다 갱신 (경과 시간 표시용)
}

/** 3초마다 방문자 상태를 받는다. demo면 서버를 부르지 않고 가상 상태를 만든다 */
export function useVisitorData(demo: boolean): VisitorData {
  const [data, setData] = useState<Omit<VisitorData, 'now' | 'guide'>>({ state: null, receivedAt: null, problem: false, closed: false })
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(performance.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    const started = performance.now()
    const poll = async () => {
      if (demo) {
        setData({ state: demoVisitorState((performance.now() - started) / 1000), receivedAt: performance.now(), problem: false, closed: false })
      } else {
        controller = new AbortController()
        const abort = setTimeout(() => controller!.abort(), TIMEOUT_MS)
        try {
          const response = await fetch('/api/v1/visitor/state', { signal: controller.signal, cache: 'no-store' })
          if (response.status === 404) {
            if (!stopped) setData(prev => ({ ...prev, closed: true, problem: false }))
          } else {
            const state = response.ok ? parseVisitorState(await response.json()) : null
            if (!stopped) setData(prev => state ? { state, receivedAt: performance.now(), problem: false, closed: false } : { ...prev, problem: true, closed: false })
          }
        } catch {
          if (!stopped) setData(prev => ({ ...prev, problem: true }))
        } finally {
          clearTimeout(abort)
        }
      }
      if (!stopped) timer = setTimeout(poll, VISITOR_POLL_MS)
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [demo])
  // 안내 약도: 상태의 판(revision)이 바뀔 때만 받는다. 못 받으면 지난 약도를 그대로 둔다
  const [guide, setGuide] = useState<VisitorGuide | null>(null)
  const wanted = data.state?.guide ?? null
  useEffect(() => {
    if (wanted === null) { if (data.state) setGuide(null); return }
    if (guide?.revision === wanted) return
    if (demo) { setGuide(demoVisitorGuide()); return }
    const controller = new AbortController()
    fetch('/api/v1/visitor/guide', { signal: controller.signal, cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(body => { const parsed = parseVisitorGuide(body); if (parsed) setGuide(parsed) })
      .catch(() => {})
    return () => controller.abort()
  }, [demo, wanted, guide?.revision, !!data.state])   // eslint-disable-line react-hooks/exhaustive-deps
  return { ...data, now, guide }
}
