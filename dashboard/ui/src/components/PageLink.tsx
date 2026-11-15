import type { ReactNode } from 'react'
import { pageHref, type PageKey } from '../navigation'

/** 화면 안 페이지로 가는 링크. 새 탭(Ctrl·⌘·가운데 클릭)은 브라우저에 맡기고, 그냥 누르면 화면을 다시 불러오지 않고 바꾼다 */
export function PageLink({ page, onNavigate, current, className, children }: { page: PageKey; onNavigate: (page: PageKey) => void; current?: boolean; className?: string; children: ReactNode }) {
  return <a href={pageHref(page)} className={className} aria-current={current ? 'page' : undefined} onClick={event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    onNavigate(page)
  }}>{children}</a>
}
