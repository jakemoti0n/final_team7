import type { PageKey } from '../../navigation'

/** 사이드바 메뉴 아이콘 (선 굵기 2, 24×24). 글자와 함께 쓰므로 읽어 주지 않는다(aria-hidden) */
export function NavIcon({ page }: { page: PageKey }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {page === 'control' && <>{/* 로봇 */}<rect x="4" y="8" width="16" height="12" rx="2" /><path d="M12 8V4" /><circle cx="12" cy="3" r="1" /><path d="M9 13v2M15 13v2" /></>}
    {page === 'fleet' && <>{/* 여러 대 */}<rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>}
    {page === 'routes' && <>{/* 경로 */}<circle cx="6" cy="19" r="3" /><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" /><circle cx="18" cy="5" r="3" /></>}
  </svg>
}
