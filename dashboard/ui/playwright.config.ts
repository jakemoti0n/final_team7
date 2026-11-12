import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8017', browserName: 'chromium', launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: '../.venv/bin/python -m uvicorn server.app:app --app-dir .. --host 127.0.0.1 --port 8017', url: 'http://127.0.0.1:8017/healthz', reuseExistingServer: false },
    // 로그인을 켠 서버 (e2e/login.spec.ts). 실행할 때마다 빈 사용자 DB에서 첫 관리자부터 시작한다
    { command: 'mkdir -p ../artifacts && rm -f ../artifacts/e2e-users.db* && ../.venv/bin/python -m uvicorn server.app:app --app-dir .. --host 127.0.0.1 --port 8018', url: 'http://127.0.0.1:8018/healthz', reuseExistingServer: false,
      env: { DASHBOARD_CONFIG: 'e2e/login-config.json', ADMIN_USERNAME: 'admin', ADMIN_PASSWORD: 'first-pass' } },
  ],
})
