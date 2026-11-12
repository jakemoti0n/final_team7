import { useEffect, useState, type FormEvent } from 'react'
import { MIN_PASSWORD, users as api, type Account, type User } from './auth'

const dateFormat = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', dateStyle: 'short', timeStyle: 'short', hour12: false })
function when(utc: string | null) { return utc ? dateFormat.format(new Date(utc)) : '없음' }

/** 회원 관리. 계정은 모두 관리자이고, 만든 계정은 임시 비밀번호라 첫 로그인 때 본인이 바꾼다 */
export default function Users({ me, onClose }: { me: Account; onClose: () => void }) {
  const [list, setList] = useState<User[] | null>(null)
  const [problem, setProblem] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [resetId, setResetId] = useState<number | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  const load = () => api.list().then(setList).catch(err => setProblem(err instanceof Error ? err.message : '회원 목록을 읽지 못했습니다.'))
  useEffect(() => { void load() }, [])
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', close)
    return () => document.removeEventListener('keydown', close)
  }, [onClose])

  const run = async (work: () => Promise<string>) => {
    if (busy) return
    setBusy(true); setProblem(''); setNotice('')
    try { setNotice(await work()); await load() } catch (err) { setProblem(err instanceof Error ? err.message : '처리하지 못했습니다.') } finally { setBusy(false) }
  }
  const add = (event: FormEvent) => {
    event.preventDefault()
    if (password.length < MIN_PASSWORD) { setProblem(`임시 비밀번호는 ${MIN_PASSWORD}자 이상이어야 합니다.`); return }
    void run(async () => {
      const created = await api.create(username.trim(), password, displayName.trim())
      setUsername(''); setDisplayName(''); setPassword('')
      return `${created.username} 계정을 만들었습니다. 임시 비밀번호를 본인에게 전달하세요. 첫 로그인 때 새 비밀번호로 바꾸게 됩니다.`
    })
  }
  const reset = (event: FormEvent, user: User) => {
    event.preventDefault()
    if (resetPassword.length < MIN_PASSWORD) { setProblem(`임시 비밀번호는 ${MIN_PASSWORD}자 이상이어야 합니다.`); return }
    void run(async () => {
      await api.update(user.id, { password: resetPassword })
      setResetId(null); setResetPassword('')
      return `${user.username}의 비밀번호를 초기화했습니다. 그 계정의 로그인은 모두 끊겼고, 다음 로그인 때 새 비밀번호로 바꾸게 됩니다.`
    })
  }
  const toggle = (user: User) => run(async () => {
    await api.update(user.id, { active: !user.active })
    return user.active ? `${user.username} 계정을 사용 중지했습니다. 그 계정의 로그인은 모두 끊겼습니다.` : `${user.username} 계정을 다시 사용할 수 있습니다.`
  })
  const remove = (user: User) => {
    if (!window.confirm(`${user.username} 계정을 삭제할까요? 되돌릴 수 없습니다.`)) return
    void run(async () => { await api.remove(user.id); return `${user.username} 계정을 삭제했습니다.` })
  }

  return <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="users-title" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
    <section className="card users-card">
      <div className="users-head"><h2 id="users-title">회원 관리</h2><button type="button" onClick={onClose} aria-label="회원 관리 닫기">닫기</button></div>
      <p className="muted">모든 계정은 관리자입니다. 관제 조작과 회원 관리를 모두 할 수 있으니 믿을 수 있는 사람에게만 만들어 주세요.</p>
      {notice && <p className="auth-notice" role="status">{notice}</p>}
      {problem && <p className="auth-error" role="alert">{problem}</p>}
      <form className="user-add" onSubmit={add} aria-label="계정 추가">
        <label>아이디<input autoComplete="off" autoCapitalize="none" spellCheck={false} required pattern="[A-Za-z0-9_.\-]{3,32}" title="영문·숫자·_.- 3~32자" value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>이름 (선택)<input autoComplete="off" maxLength={64} value={displayName} onChange={e => setDisplayName(e.target.value)} /></label>
        <label>임시 비밀번호<input type="text" autoComplete="new-password" required minLength={MIN_PASSWORD} value={password} onChange={e => setPassword(e.target.value)} /></label>
        <button type="submit" className="primary" disabled={busy}>계정 추가</button>
      </form>
      {list === null ? <p className="empty">{problem ? '목록을 표시할 수 없습니다' : '불러오는 중…'}</p> : <ul className="user-list" aria-label="계정 목록">
        {list.map(user => {
          const self = user.id === me.id
          return <li key={user.id} className={user.active ? '' : 'inactive'}>
            <div className="user-name"><strong>{user.username}</strong>{user.display_name && <span>{user.display_name}</span>}{self && <span className="mode-tag">나</span>}
              <span className={`badge ${user.active ? 'good' : 'neutral'}`}>{user.active ? '사용 중' : '사용 중지'}</span>{user.must_change_password && <span className="badge warn">임시 비밀번호</span>}</div>
            <small>마지막 로그인 {when(user.last_login_at)} · 만든 날 {when(user.created_at)}</small>
            {resetId === user.id ? <form className="user-reset" onSubmit={e => reset(e, user)}>
              <label>새 임시 비밀번호<input type="text" autoComplete="new-password" required minLength={MIN_PASSWORD} value={resetPassword} onChange={e => setResetPassword(e.target.value)} autoFocus /></label>
              <button type="submit" className="primary" disabled={busy}>초기화</button><button type="button" onClick={() => { setResetId(null); setResetPassword('') }}>취소</button>
            </form> : <div className="user-actions">
              {!self && <button type="button" disabled={busy} onClick={() => { setResetId(user.id); setResetPassword('') }}>비밀번호 초기화</button>}
              {!self && <button type="button" disabled={busy} onClick={() => void toggle(user)}>{user.active ? '사용 중지' : '다시 사용'}</button>}
              {!self && <button type="button" className="danger" disabled={busy} onClick={() => remove(user)}>삭제</button>}
              {self && <small>내 비밀번호는 위쪽의 「비밀번호 변경」에서 바꿉니다.</small>}
            </div>}
          </li>
        })}
      </ul>}
    </section>
  </div>
}
