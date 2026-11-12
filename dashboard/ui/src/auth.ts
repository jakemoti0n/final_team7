// 화면 로그인. 서버가 세션 쿠키(HttpOnly)를 붙이므로 화면은 토큰을 직접 다루지 않는다.
// 계정은 모두 관리자 한 등급이다 (관제 조작과 회원 관리를 모두 할 수 있음)

export type Account = { id: number; username: string; display_name: string; must_change_password: boolean }
export type AuthState = { loginRequired: boolean; user: Account | null }
export type User = Account & { active: boolean; created_at: string; updated_at: string; last_login_at: string | null }

const lost = new Set<() => void>()
/** 로그인이 끝났을 수 있을 때(401·403) 부른다. 화면은 /auth/me를 다시 물어 로그인 화면으로 돌아갈지 정한다 */
export function onAuthLost(fn: () => void) { lost.add(fn); return () => { lost.delete(fn) } }

/** fetch와 같다. 응답이 401이나 403이면 onAuthLost 구독자에게 알린다 */
export async function api(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init)
  if (response.status === 401 || response.status === 403) lost.forEach(fn => fn())
  return response
}

const messages: Record<string, string> = {
  invalid_credentials: '아이디 또는 비밀번호가 맞지 않습니다.',
  too_many_attempts: '로그인 실패가 많아 잠시 막혔습니다. 5분쯤 뒤에 다시 시도하세요.',
  login_required: '로그인이 끝났습니다. 다시 로그인해 주세요.',
  cross_site_request: '다른 사이트에서 보낸 요청이라 거절했습니다. 이 주소에서 직접 다시 시도하세요.',
}
/** 서버 오류 본문을 화면 문구로. 회원 관리 오류는 서버가 한국어 문구를 준다 */
export async function errorText(response: Response, fallback: string) {
  const body = await response.json().catch(() => null)
  const code = body?.error?.code
  return messages[code] ?? (typeof body?.error?.message === 'string' && /[가-힣]/.test(body.error.message) ? body.error.message : `${fallback} (${response.status})`)
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), cache: 'no-store' }
}
function parse(value: unknown): AuthState {
  const v = value as { login_required?: unknown; user?: Account | null } | null
  return { loginRequired: v?.login_required !== false, user: v?.user ?? null }
}

/** 지금 로그인 상태. 서버에 닿지 못하면 예외 */
export async function me(): Promise<AuthState> {
  const response = await fetch('/api/v1/auth/me', { cache: 'no-store' })
  if (response.status === 401) return { loginRequired: true, user: null }
  if (!response.ok) throw new Error(`auth/me ${response.status}`)
  return parse(await response.json())
}

/** 성공하면 로그인 상태, 실패하면 화면에 보일 문구를 담은 Error */
export async function login(username: string, password: string): Promise<AuthState> {
  let response: Response
  try { response = await fetch('/api/v1/auth/login', json('POST', { username, password })) } catch { throw new Error('서버에 연결할 수 없습니다.') }
  if (!response.ok) throw new Error(await errorText(response, '로그인하지 못했습니다'))
  return parse(await response.json())
}

export async function logout() {
  await fetch('/api/v1/auth/logout', { method: 'POST', cache: 'no-store' }).catch(() => null)
}

export async function changePassword(current: string, next: string): Promise<AuthState> {
  let response: Response
  // 현재 비밀번호가 틀리면 403(wrong_password)이므로 api()가 아닌 fetch로 (로그인이 끝난 것으로 보지 않게)
  try { response = await fetch('/api/v1/auth/password', json('PUT', { current_password: current, new_password: next })) } catch { throw new Error('서버에 연결할 수 없습니다.') }
  if (!response.ok) throw new Error(await errorText(response, '비밀번호를 바꾸지 못했습니다'))
  return parse(await response.json())
}

export const MIN_PASSWORD = 5

// ---- 회원 관리 ----

async function call<T>(input: string, init: RequestInit | undefined, fallback: string): Promise<T> {
  let response: Response
  try { response = await api(input, init) } catch { throw new Error('서버에 연결할 수 없습니다.') }
  if (!response.ok) throw new Error(await errorText(response, fallback))
  return response.status === 204 ? (undefined as T) : response.json()
}
export const users = {
  list: () => call<{ users: User[] }>('/api/v1/users', { cache: 'no-store' }, '회원 목록을 읽지 못했습니다').then(v => v.users),
  create: (username: string, password: string, display_name: string) => call<User>('/api/v1/users', json('POST', { username, password, display_name }), '계정을 만들지 못했습니다'),
  update: (id: number, change: Partial<{ display_name: string; active: boolean; password: string }>) => call<User>(`/api/v1/users/${id}`, json('PATCH', change), '계정을 바꾸지 못했습니다'),
  remove: (id: number) => call<void>(`/api/v1/users/${id}`, { method: 'DELETE', cache: 'no-store' }, '계정을 지우지 못했습니다'),
}
