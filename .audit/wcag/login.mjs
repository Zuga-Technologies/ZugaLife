// One-shot login → persist storage-state.json for the scanner.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve as pResolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = pResolve(__dirname, '..', '..')
const env = Object.fromEntries(
  readFileSync(pResolve(REPO_ROOT, '.audit', 'creds.env'), 'utf8')
    .split('\n').filter(l => l && !l.startsWith('#'))
    .map(l => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)] })
)
const BASE = env.AUDIT_BASE_URL || 'https://zugabot.ai'

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await ctx.newPage()

// /life triggers redirect to ZugaApp's custom /login form.
await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2000)

const email = page.locator('input[type="email"]').first()
const pw = page.locator('input[type="password"]').first()
await email.waitFor({ state: 'visible', timeout: 15000 })
await email.fill(env.AUDIT_EMAIL)
await pw.fill(env.AUDIT_PASSWORD)

const submit = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Log in"), button:has-text("SIGN IN")').first()
await submit.click({ timeout: 8000 })

await page.waitForURL(u => !String(u).includes('/login'), { timeout: 20000 }).catch(() => {})
await page.waitForTimeout(2000)

console.log('post-login url:', page.url())

await ctx.storageState({ path: pResolve(REPO_ROOT, '.audit', 'storage-state.json') })
console.log('storage-state.json written')

await ctx.close()
await browser.close()
