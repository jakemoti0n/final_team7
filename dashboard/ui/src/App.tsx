import { useCallback, useEffect, useRef, useState } from 'react'
import type { RobotSummary } from './types'
import { api, logout, me, onAuthLost, type Account, type AuthState } from './auth'
import Login from './Login'
import ChangePassword from './ChangePassword'
import { RobotDashboard } from './pages/RobotDashboard'
import { mayLeave, pageHref, readPage, type PageKey } from './navigation'
import { VisitorPage } from './pages/VisitorPage'

const ROBOT_KEY = 'limbo.robot'
/** 처음 볼 로봇: 주소의 ?robot= → 이 브라우저에서 마지막으로 고른 로봇 → 비움(서버 기본 로봇) */
function initialRobot() {
  const fromUrl = new URLSearchParams(location.search).get('robot')
  if (fromUrl) return fromUrl
  try { return localStorage.getItem(ROBOT_KEY) ?? '' } catch { return '' }
}
/** 로그인 확인 후 관제 화면. 데모(/demo)는 서버를 쓰지 않으므로 로그인 없이 바로 연다.
 *  방문자 안내(/visitor)는 로그인 없이 읽기 전용 (?demo면 가상 데이터) */
export default function App() {
  if (location.pathname === '/visitor') {
    document.title = 'LIMBO 실시간 안내'   // 방문객 휴대폰 탭·북마크에 보이는 이름 (index.html 기본값은 운영자용 'LIMBO 관제')
    return <VisitorPage demo={new URLSearchParams(location.search).has('demo')} />
  }
  if (location.pathname === '/demo') return <RobotApp account={null} onAuth={() => {}} />
  return <AuthGate />
}
type Gate = AuthState | 'checking' | 'unreachable'
function AuthGate() {
  const [auth, setAuth] = useState<Gate>('checking')
  const [notice, setNotice] = useState('')
  const check = useCallback(() => {
    me().then(next => setAuth(prev => {
      // 로그인해 있던 화면이 로그인 화면으로 돌아가면 이유를 알려 준다
      if (typeof prev === 'object' && prev.user && !next.user) setNotice('로그인이 끝났습니다(로그아웃·만료·계정 변경). 다시 로그인해 주세요.')
      return next
    })).catch(() => setAuth(prev => typeof prev === 'object' ? prev : 'unreachable'))
  }, [])
  useEffect(() => { check(); return onAuthLost(check) }, [check])
  useEffect(() => {
    if (auth !== 'unreachable') return
    const timer = setTimeout(check, 5000)   // 서버가 다시 뜨면 저절로 이어진다
    return () => clearTimeout(timer)
  }, [auth, check])
  const signOut = () => { void logout().then(() => { setNotice('로그아웃했습니다.'); setAuth({ loginRequired: true, user: null }) }) }
  if (auth === 'checking') return <main className="auth-page"><p className="muted" role="status">로그인 상태를 확인하고 있습니다…</p></main>
  if (auth === 'unreachable') return <main className="auth-page"><div className="card auth-card" role="alert"><h1>LIMBO 관제</h1><p>관제 서버에 연결할 수 없습니다. 5초마다 다시 시도합니다.</p><button type="button" onClick={check}>지금 다시 시도</button></div></main>
  if (auth.loginRequired && !auth.user) return <Login notice={notice} onDone={next => { setNotice(''); setAuth(next) }} />
  if (auth.user?.must_change_password) return <ChangePassword forced username={auth.user.username} onDone={setAuth} onCancel={signOut} />
  return <RobotApp account={auth.user} onAuth={next => next === null ? signOut() : setAuth(next)} />
}
/** account: 로그인한 계정 (로그인 없이 연 서버·데모면 null). onAuth(null)은 로그아웃 */
function RobotApp({ account, onAuth }: { account: Account | null; onAuth: (next: AuthState | null) => void }) {
  const demoMode = location.pathname === '/demo'
  const [robotId, setRobotId] = useState(() => demoMode ? '' : initialRobot())
  // 페이지는 로봇을 바꿔도 유지한다. 주소(?page=)에 남겨 새로 고침·뒤로 가기에도 맞춘다
  const [page, setPage] = useState<PageKey>(() => readPage())
  useEffect(() => {
    const sync = () => {
      // 뒤로 가기는 막을 수 없으므로, 머물기로 하면 주소를 지금 페이지로 되돌린다
      if (!mayLeave()) { history.pushState(null, '', pageHref(pageRef.current)); return }
      setPage(readPage())
    }
    addEventListener('popstate', sync)
    return () => removeEventListener('popstate', sync)
  }, [])
  const pageRef = useRef(page)
  pageRef.current = page
  const navigate = (next: PageKey) => {
    if (next === readPage() || !mayLeave()) return
    history.pushState(null, '', pageHref(next))
    setPage(next)
    scrollTo(0, 0)
  }
  const choose = (next: string) => {
    if (next !== robotId && !mayLeave()) return
    setRobotId(next)
    const url = new URL(location.href)
    if (next) url.searchParams.set('robot', next); else url.searchParams.delete('robot')
    history.replaceState(null, '', url)
    try { if (next) localStorage.setItem(ROBOT_KEY, next); else localStorage.removeItem(ROBOT_KEY) } catch { /* 저장 못 해도 화면은 동작 */ }
  }
  useEffect(() => {
    // 저장된 로봇을 서버가 모르면(서버 재시작 등) 기본 로봇으로 되돌린다
    if (demoMode || !robotId) return
    const controller = new AbortController()
    api('/api/v1/robots', { signal: controller.signal }).then(r => r.ok ? r.json() : null).then(value => {
      if (Array.isArray(value?.robots) && !value.robots.some((r: RobotSummary) => r.robot_id === robotId)) choose('')
    }).catch(() => {})
    return () => controller.abort()
  }, [demoMode, robotId])
  return <RobotDashboard key={robotId} robotId={robotId} onSelect={choose} account={account} onAuth={onAuth} page={page} onNavigate={navigate} />
}
