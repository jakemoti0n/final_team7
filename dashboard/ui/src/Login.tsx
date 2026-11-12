import { useState, type FormEvent } from 'react'
import { login, type AuthState } from './auth'

/** 로그인 화면. 계정은 관리자가 회원 관리에서 만들어 준다 (자가 가입 없음) */
export default function Login({ onDone, notice }: { onDone: (state: AuthState) => void; notice?: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true); setProblem('')
    try { onDone(await login(username.trim(), password)) } catch (err) { setProblem(err instanceof Error ? err.message : '로그인하지 못했습니다.'); setPassword('') } finally { setBusy(false) }
  }
  return <main className="auth-page">
    <form className="card auth-card" onSubmit={submit} aria-labelledby="login-title">
      <h1 id="login-title">LIMBO 관제</h1>
      <p className="muted">관리자 계정으로 로그인하세요. 계정이 없으면 다른 관리자에게 만들어 달라고 요청하세요.</p>
      {notice && !problem && <p className="auth-notice" role="status">{notice}</p>}
      <label>아이디<input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} required value={username} onChange={e => setUsername(e.target.value)} autoFocus /></label>
      <label>비밀번호<input name="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
      {problem && <p className="auth-error" role="alert">{problem}</p>}
      <button type="submit" className="primary" disabled={busy || !username.trim() || !password}>{busy ? '확인 중…' : '로그인'}</button>
      <a href="/demo">로그인 없이 가상 제어 데모 보기 →</a>
    </form>
  </main>
}
