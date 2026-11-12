import { useState, type FormEvent } from 'react'
import { changePassword, MIN_PASSWORD, type AuthState } from './auth'

/** 비밀번호 변경. forced면 첫 로그인(임시 비밀번호)이라 바꾸기 전에는 관제 화면을 쓸 수 없다 */
export default function ChangePassword({ forced, username, onDone, onCancel }: { forced: boolean; username: string; onDone: (state: AuthState) => void; onCancel: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)
  const mismatch = again !== '' && next !== again
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    if (next.length < MIN_PASSWORD) { setProblem(`새 비밀번호는 ${MIN_PASSWORD}자 이상이어야 합니다.`); return }
    if (next !== again) { setProblem('새 비밀번호 두 칸이 다릅니다.'); return }
    setBusy(true); setProblem('')
    try { onDone(await changePassword(current, next)) } catch (err) { setProblem(err instanceof Error ? err.message : '비밀번호를 바꾸지 못했습니다.') } finally { setBusy(false) }
  }
  const form = <form className="card auth-card" onSubmit={submit} aria-labelledby="password-title">
    <h1 id="password-title">비밀번호 변경</h1>
    <p className="muted">{forced ? `${username} 계정은 임시 비밀번호입니다. 새 비밀번호로 바꾼 뒤 관제 화면을 쓸 수 있습니다.` : '바꾸면 다른 기기에서 로그인한 세션은 모두 끊깁니다.'}</p>
    <input type="text" name="username" autoComplete="username" value={username} readOnly hidden />
    <label>현재 비밀번호{forced && ' (임시 비밀번호)'}<input type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} autoFocus /></label>
    <label>새 비밀번호 ({MIN_PASSWORD}자 이상)<input type="password" autoComplete="new-password" required minLength={MIN_PASSWORD} value={next} onChange={e => setNext(e.target.value)} /></label>
    <label>새 비밀번호 확인<input type="password" autoComplete="new-password" required value={again} onChange={e => setAgain(e.target.value)} aria-invalid={mismatch} /></label>
    {mismatch && !problem && <small>새 비밀번호 두 칸이 다릅니다.</small>}
    {problem && <p className="auth-error" role="alert">{problem}</p>}
    <div className="auth-actions">
      <button type="submit" className="primary" disabled={busy || !current || !next || !again}>{busy ? '바꾸는 중…' : '비밀번호 바꾸기'}</button>
      <button type="button" onClick={onCancel}>{forced ? '로그아웃' : '취소'}</button>
    </div>
  </form>
  return forced ? <main className="auth-page">{form}</main> : <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="password-title">{form}</div>
}
