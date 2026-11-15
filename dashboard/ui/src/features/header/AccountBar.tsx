import { useCallback, useState } from 'react'
import type { Account, AuthState } from '../../auth'
import ChangePassword from '../../ChangePassword'
import Users from '../../Users'

/** 헤더 오른쪽 계정 메뉴: 이름 · 회원 관리 · 비밀번호 변경 · 로그아웃 */
export function AccountBar({ account, onAuth }: { account: Account; onAuth: (next: AuthState | null) => void }) {
  const [panel, setPanel] = useState<'users' | 'password' | null>(null)
  const close = useCallback(() => setPanel(null), [])
  return <div className="account" data-testid="account">
    <span className="account-name" data-testid="account-name" title={account.display_name || undefined}>{account.username}</span>
    <button type="button" onClick={() => setPanel('users')}>회원 관리</button>
    <button type="button" onClick={() => setPanel('password')}>비밀번호 변경</button>
    <button type="button" onClick={() => onAuth(null)}>로그아웃</button>
    {panel === 'users' && <Users me={account} onClose={close} />}
    {panel === 'password' && <ChangePassword forced={false} username={account.username} onDone={next => { setPanel(null); onAuth(next) }} onCancel={close} />}
  </div>
}
