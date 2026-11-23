import { useEffect, useState } from 'react'
import { demoVisitorState, parseVisitorState, type VisitorState } from '../visitor/visitor'
import { VISITOR_POLL_MS } from '../visitor/useVisitorData'
import { demoDisplayContent, parseDisplayContent, type DisplayContent } from './display'

const TIMEOUT_MS = 5000

export interface DisplayData {
  state: VisitorState | null       // 마지막으로 받은 방문자 상태 (못 받게 되어도 남겨 둔다)
  problem: boolean                 // 마지막 요청이 실패했거나 응답 모양이 이상함
  closed: boolean                  // 서버가 방문자·디스플레이를 껐다 (404)
  content: DisplayContent | null   // 일정·팜플렛·장면 길이. 서버에 없으면 null (기본 길이로 ①만)
}

/**
 * 하단 디스플레이 데이터. 방문자 상태(/api/v1/visitor/state)를 3초마다 받고,
 * 그 안의 display 판이 바뀔 때만 내용(/api/v1/display/content)을 다시 받는다. demo면 서버를 부르지 않는다.
 */
export function useDisplayData(demo: boolean): DisplayData {
  const [data, setData] = useState<Omit<DisplayData, 'content'>>({ state: null, problem: false, closed: false })
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    const started = performance.now()
    const poll = async () => {
      if (demo) {
        setData({ state: demoVisitorState((performance.now() - started) / 1000), problem: false, closed: false })
      } else {
        controller = new AbortController()
        const abort = setTimeout(() => controller!.abort(), TIMEOUT_MS)
        try {
          const response = await fetch('/api/v1/visitor/state', { signal: controller.signal, cache: 'no-store' })
          if (response.status === 404) {
            if (!stopped) setData(prev => ({ ...prev, closed: true, problem: false }))
          } else {
            const state = response.ok ? parseVisitorState(await response.json()) : null
            if (!stopped) setData(prev => state ? { state, problem: false, closed: false } : { ...prev, problem: true, closed: false })
          }
        } catch {
          if (!stopped) setData(prev => ({ ...prev, problem: true }))
        } finally {
          clearTimeout(abort)
        }
      }
      if (!stopped) timer = setTimeout(poll, demo ? 1000 : VISITOR_POLL_MS)   // 데모는 「지나갑니다」가 매끄럽게 1초마다
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer); controller?.abort() }
  }, [demo])

  // 내용: 판이 바뀔 때만 받는다. 못 받으면 지난 내용을 그대로 둔다(화면은 계속 돈다). 판이 null이면(서버에 내용 없음) 비운다
  const [content, setContent] = useState<DisplayContent | null>(null)
  const wanted = data.state ? data.state.display ?? null : undefined
  useEffect(() => {
    if (wanted === undefined) return
    if (wanted === null) { setContent(null); return }
    if (content?.revision === wanted) return
    if (demo) { setContent(demoDisplayContent()); return }
    const controller = new AbortController()
    fetch('/api/v1/display/content', { signal: controller.signal, cache: 'no-store' })
      .then(r => r.ok ? r.json() : null).then(body => { const parsed = parseDisplayContent(body); if (parsed) setContent(parsed) })
      .catch(() => {})
    return () => controller.abort()
    // 상태를 받을 때마다 다시 본다: 받기에 실패했으면 다음 상태 때 다시 시도 (같은 판을 이미 가졌으면 바로 끝)
  }, [demo, wanted, content?.revision, data.state])   // eslint-disable-line react-hooks/exhaustive-deps
  return { ...data, content }
}
