import type { ReactNode } from 'react'
import { pages, type PageKey } from '../../navigation'
import { PageLink } from '../../components/PageLink'
import { NavIcon } from './NavIcon'

/** 왼쪽 사이드바: 제품 이름, 관제할 로봇 고르기, 페이지 메뉴. 좁은 화면에서는 화면 위쪽 띠가 된다 */
export function Sidebar({ page, onNavigate, picker, demo }: { page: PageKey; onNavigate: (page: PageKey) => void; picker: ReactNode; demo: boolean }) {
  return <aside className="sidebar"><div className="sidebar-inner">
    <div className="sidebar-brand"><span className="brand-mark" aria-hidden="true">L</span><span><strong>LIMBO 관제</strong><small>순찰 로봇 관제 화면</small></span></div>
    <div className="sidebar-target"><span className="sidebar-label" id="target-label">관제 대상 로봇</span>{picker}{demo && <span className="mode-tag">데모 데이터</span>}</div>
    <nav aria-label="관제 메뉴"><ul className="sidebar-nav">{pages.map(p => <li key={p.key}>
      <PageLink page={p.key} current={p.key === page} onNavigate={onNavigate} className="nav-item"><NavIcon page={p.key} />{p.label}</PageLink>
    </li>)}</ul></nav>
    <a className="sidebar-switch" href={demo ? '/' : '/demo'}>{demo ? '실제 수신 화면으로 →' : '가상 제어 데모 보기 →'}</a>
  </div></aside>
}
