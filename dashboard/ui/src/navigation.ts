/**
 * 화면 안의 페이지(사이드바 메뉴). 서버는 / 와 /demo 만 화면을 주므로 주소의 ?page= 로 나눈다.
 * 로봇 선택(?robot=)과 함께 쓰며, 뒤로 가기로 이전 페이지에 돌아간다.
 */
export type PageKey = 'control' | 'fleet' | 'routes' | 'guide'

export const pages: { key: PageKey; label: string; summary: string }[] = [
  { key: 'control', label: '로봇 관제', summary: '선택한 로봇의 상태 확인 · 순찰 제어' },
  { key: 'fleet', label: '플릿 현황', summary: '서버에 연결된 로봇 전체의 연결 상태와 위치' },
  { key: 'routes', label: '순찰 경로', summary: '순찰 waypoint 확인 · 편집 (다음 순찰 시작 때 적용)' },
  { key: 'guide', label: '약도 편집', summary: '방문자 화면에 보일 구역·이름 그리기 (기본 로봇 지도 기준)' },
]

export function readPage(search = location.search): PageKey {
  const value = new URLSearchParams(search).get('page')
  return value === 'fleet' || value === 'routes' || value === 'guide' ? value : 'control'
}

/**
 * 떠나기 전 확인 (약도 편집에 저장하지 않은 변경이 있을 때). 페이지 이동·로봇 바꾸기·뒤로 가기가 이것을 거친다.
 * guard가 false를 돌려주면 머문다
 */
let leaveGuard: (() => boolean) | null = null
export function setLeaveGuard(guard: (() => boolean) | null) { leaveGuard = guard }
export function mayLeave() { return !leaveGuard || leaveGuard() }

/** 지금 주소에서 page만 바꾼 주소 (로봇 관제는 page 없이) */
export function pageHref(page: PageKey, href = location.href) {
  const url = new URL(href)
  if (page === 'control') url.searchParams.delete('page'); else url.searchParams.set('page', page)
  return url.pathname + url.search
}
