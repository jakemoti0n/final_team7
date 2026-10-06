import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8017', browserName: 'chromium', launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: '../.venv/bin/python -m uvicorn server.app:app --app-dir .. --host 127.0.0.1 --port 8017', url: 'http://127.0.0.1:8017/healthz', reuseExistingServer: false },
})
