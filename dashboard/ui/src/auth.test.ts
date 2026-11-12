import { afterEach, expect, it, vi } from 'vitest'
import { api, changePassword, errorText, login, me, onAuthLost, users } from './auth'

function reply(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('api tells listeners when the login may have ended (401/403), not on other errors', async () => {
  const lost = vi.fn()
  const off = onAuthLost(lost)
  const responses = [reply(200), reply(409), reply(401), reply(403)]
  vi.stubGlobal('fetch', vi.fn(async () => responses.shift()))
  for (let i = 0; i < 4; i++) await api('/api/v1/state')
  expect(lost).toHaveBeenCalledTimes(2)
  off()
  vi.stubGlobal('fetch', vi.fn(async () => reply(401)))
  await api('/api/v1/state')
  expect(lost).toHaveBeenCalledTimes(2)
})

it('me reads login state: logged in, logged out, or a server without login', async () => {
  const user = { id: 1, username: 'admin', display_name: '', must_change_password: false }
  vi.stubGlobal('fetch', vi.fn(async () => reply(200, { login_required: true, user })))
  expect(await me()).toEqual({ loginRequired: true, user })
  vi.stubGlobal('fetch', vi.fn(async () => reply(401, { error: { code: 'login_required' } })))
  expect(await me()).toEqual({ loginRequired: true, user: null })
  vi.stubGlobal('fetch', vi.fn(async () => reply(200, { login_required: false, user: null })))
  expect(await me()).toEqual({ loginRequired: false, user: null })
  vi.stubGlobal('fetch', vi.fn(async () => reply(502)))
  await expect(me()).rejects.toThrow()
})

it('login and password change turn server errors into screen text', async () => {
  const fetch = vi.fn(async () => reply(401, { error: { code: 'invalid_credentials', message: 'Wrong username or password' } }))
  vi.stubGlobal('fetch', fetch)
  await expect(login('admin', 'x')).rejects.toThrow('아이디 또는 비밀번호가 맞지 않습니다.')
  expect(fetch).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ method: 'POST', body: JSON.stringify({ username: 'admin', password: 'x' }) }))
  vi.stubGlobal('fetch', vi.fn(async () => reply(429, { error: { code: 'too_many_attempts' } })))
  await expect(login('admin', 'x')).rejects.toThrow('5분')
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
  await expect(login('admin', 'x')).rejects.toThrow('서버에 연결할 수 없습니다.')
  const lost = vi.fn(); const off = onAuthLost(lost)
  vi.stubGlobal('fetch', vi.fn(async () => reply(403, { error: { code: 'wrong_password', message: '현재 비밀번호가 맞지 않습니다' } })))
  await expect(changePassword('a', 'bbbbb')).rejects.toThrow('현재 비밀번호가 맞지 않습니다')
  expect(lost).not.toHaveBeenCalled()   // 틀린 현재 비밀번호는 로그인이 끝난 것이 아니다
  off()
})

it('user management calls the API and shows Korean server messages, English ones with the status', async () => {
  const fetch = vi.fn(async () => reply(204))
  vi.stubGlobal('fetch', fetch)
  await users.remove(3)
  expect(fetch).toHaveBeenCalledWith('/api/v1/users/3', expect.objectContaining({ method: 'DELETE' }))
  vi.stubGlobal('fetch', vi.fn(async () => reply(409, { error: { code: 'cannot_delete_self', message: '자기 계정은 삭제할 수 없습니다' } })))
  await expect(users.remove(1)).rejects.toThrow('자기 계정은 삭제할 수 없습니다')
  expect(await errorText(reply(500, { error: { code: 'server_error', message: 'Internal server error' } }), '실패')).toBe('실패 (500)')
})
