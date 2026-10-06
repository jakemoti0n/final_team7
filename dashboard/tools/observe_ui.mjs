// JSON-lines observer used by the ROS integration harness. No product test hooks.
import { chromium } from '../ui/node_modules/@playwright/test/index.mjs'
import readline from 'node:readline'
const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {})
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
await page.goto(process.argv[2])
await page.locator('.connection .badge').filter({ hasText: '연결됨' }).waitFor()
console.log(JSON.stringify({ ready: true }))
try {
  for await (const line of readline.createInterface({ input: process.stdin })) {
    const input = JSON.parse(line)
    if (input.quit) break
    try {
      await page.waitForFunction(expected => {
        const speed = document.querySelector('.speed strong')?.textContent
        const movement = document.querySelector('.movement')?.textContent
        const retained = document.querySelector('.speed')?.textContent?.includes('마지막 수신 값')
        return speed === expected.speed && movement?.includes(expected.movement) && retained === expected.retained
      }, input, { timeout: 2000, polling: 20 })
      console.log(JSON.stringify({ ok: true }))
    } catch (error) { console.log(JSON.stringify({ ok: false, error: String(error) })) }
  }
  await page.screenshot({ path: new URL('../artifacts/bridge-1440.png', import.meta.url).pathname, fullPage: true })
} finally { await browser.close(); process.stdin.destroy() }
