import { test, expect, type Page } from '@playwright/test'
// 로그인을 켠 서버(포트 8018, playwright.config.ts)에서 첫 관리자 → 비밀번호 변경 → 회원 추가 → 새 회원 첫 로그인
test.use({ baseURL: 'http://127.0.0.1:8018' })

async function signIn(page: Page, username: string, password: string) {
  await page.getByLabel('아이디').fill(username)
  await page.getByLabel('비밀번호', { exact: true }).fill(password)
  await page.getByRole('button', { name: '로그인' }).click()
}
async function changeFirstPassword(page: Page, current: string, next: string) {
  await expect(page.getByRole('heading', { name: '비밀번호 변경' })).toBeVisible()
  await page.getByLabel(/현재 비밀번호/).fill(current)
  await page.getByLabel(/^새 비밀번호 \(/).fill(next)
  await page.getByLabel('새 비밀번호 확인').fill(next)
  await page.getByRole('button', { name: '비밀번호 바꾸기' }).click()
}

test('first admin logs in, must change password, adds a member who then logs in', async ({ page, request }) => {
  expect((await request.get('/api/v1/state')).status()).toBe(401)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'LIMBO 관제' })).toBeVisible()
  await signIn(page, 'admin', 'wrong-pass')
  await expect(page.getByRole('alert')).toHaveText('아이디 또는 비밀번호가 맞지 않습니다.')

  await signIn(page, 'admin', 'first-pass')
  await changeFirstPassword(page, 'first-pass', 'admin-pass')
  await expect(page.locator('.account-name')).toHaveText('admin')
  await expect(page.locator('.last-received')).toBeVisible()           // 실시간 화면이 열렸다 (입장표·WebSocket)
  await expect(page.locator('.banner')).not.toContainText('서버 상태를 갱신할 수 없습니다', { timeout: 5000 })

  await page.getByRole('button', { name: '회원 관리' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('아이디').fill('kim')
  await dialog.getByLabel('이름 (선택)').fill('김관제')
  await dialog.getByLabel('임시 비밀번호').fill('kim-temp')
  await dialog.getByRole('button', { name: '계정 추가' }).click()
  await expect(dialog.getByRole('status')).toContainText('kim 계정을 만들었습니다')
  const kim = dialog.locator('.user-list li', { hasText: 'kim' })
  await expect(kim).toContainText('임시 비밀번호')
  const self = dialog.locator('.user-list li', { hasText: '나' })
  await expect(self.getByRole('button', { name: '삭제' })).toHaveCount(0)   // 자기 계정은 지울 수 없다
  await dialog.getByRole('button', { name: '회원 관리 닫기' }).click()

  await page.getByRole('button', { name: '로그아웃' }).click()
  await expect(page.locator('.auth-notice')).toHaveText('로그아웃했습니다.')
  await signIn(page, 'kim', 'kim-temp')
  await changeFirstPassword(page, 'kim-temp', 'kim-pass')
  await expect(page.locator('.account-name')).toHaveText('kim')
  const cookies = await page.context().cookies()
  expect(cookies.find(c => c.name === 'limbo_session')).toMatchObject({ httpOnly: true, sameSite: 'Strict' })
})

test('demo stays open without login', async ({ page }) => {
  await page.goto('/demo')
  await expect(page.getByText('데모 데이터 · 실제 로봇을 제어하지 않습니다')).toBeVisible()
  await expect(page.locator('.account')).toHaveCount(0)
})
