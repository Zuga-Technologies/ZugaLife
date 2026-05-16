// WCAG 2.1 AA baseline scanner — ZugaLife Issue #3 T12
// Logs in once, iterates routes, runs axe-core per route, dumps JSON + ASCII table.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve as pResolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import AxeBuilder from '@axe-core/playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = pResolve(__dirname, '..', '..')
const AUDIT_DIR = pResolve(REPO_ROOT, '.audit', 'wcag')
const STATE_FILE = pResolve(REPO_ROOT, '.audit', 'storage-state.json')
const CREDS_FILE = pResolve(REPO_ROOT, '.audit', 'creds.env')

const env = Object.fromEntries(
  readFileSync(CREDS_FILE, 'utf8')
    .split('\n')
    .filter(l => l && !l.startsWith('#'))
    .map(l => {
      const i = l.indexOf('=')
      return [l.slice(0, i), l.slice(i + 1)]
    })
)

const BASE = env.AUDIT_BASE_URL || 'https://zugabot.ai'
const ROUTES = [
  { slug: 'life-dashboard', path: '/life' },
  { slug: 'life-journal', path: '/life/journal' },
  { slug: 'life-habits', path: '/life/habits' },
  { slug: 'life-goals', path: '/life/goals' },
  { slug: 'life-meditate', path: '/life/meditate' },
  { slug: 'life-therapist', path: '/life/therapist' },
  { slug: 'life-settings', path: '/life/settings' },
]

if (!existsSync(AUDIT_DIR)) mkdirSync(AUDIT_DIR, { recursive: true })

const browser = await chromium.launch({ headless: true })

async function login() {
  console.log('[login] starting fresh session')
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('#email', env.AUDIT_EMAIL)
  await page.fill('#password', env.AUDIT_PASSWORD)
  await Promise.all([
    page.waitForURL(u => !u.toString().includes('/login'), { timeout: 30000 }),
    page.click('button[type=submit]'),
  ])
  console.log(`[login] success → ${page.url()}`)
  await ctx.storageState({ path: STATE_FILE })
  await ctx.close()
}

async function scanRoute(ctx, { slug, path }) {
  const page = await ctx.newPage()
  const url = `${BASE}${path}`
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 })
  } catch (e) {
    console.log(`[${slug}] navigation slow, continuing: ${e.message.split('\n')[0]}`)
  }
  // Let SPA finish rendering (Vue + tab content).
  await page.waitForTimeout(2500)
  const finalUrl = page.url()
  const reachedLogin = finalUrl.includes('/login')
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const summary = {
    slug,
    target: url,
    final_url: finalUrl,
    reached_login: reachedLogin,
    violations: results.violations.length,
    by_impact: results.violations.reduce(
      (acc, v) => ({ ...acc, [v.impact || 'minor']: (acc[v.impact || 'minor'] || 0) + 1 }),
      {}
    ),
    rules: results.violations.map(v => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.length,
      first_target: v.nodes[0]?.target?.join(' ') || '',
    })),
    raw: results,
  }
  writeFileSync(pResolve(AUDIT_DIR, `${slug}.json`), JSON.stringify(summary, null, 2))
  await page.close()
  return summary
}

await login()

const ctx = await browser.newContext({ storageState: STATE_FILE })
const all = []
for (const r of ROUTES) {
  console.log(`[scan] ${r.path}`)
  const s = await scanRoute(ctx, r)
  all.push(s)
  console.log(`  → ${s.violations} violations  impact=${JSON.stringify(s.by_impact)}  reached_login=${s.reached_login}`)
}
await ctx.close()
await browser.close()

// Aggregate ASCII table
const pad = (s, n) => String(s).padEnd(n)
const padR = (s, n) => String(s).padStart(n)
const cnt = (s, k) => s.by_impact?.[k] || 0
const lines = []
lines.push('')
lines.push('ROUTE                VIOLS  CRIT  SERIOUS  MOD  MINOR  AUTH')
lines.push('-------------------- -----  ----  -------  ---  -----  ----')
for (const s of all) {
  lines.push(
    pad(s.target.replace(BASE, ''), 20) +
      ' ' +
      padR(s.violations, 5) +
      ' ' +
      padR(cnt(s, 'critical'), 5) +
      ' ' +
      padR(cnt(s, 'serious'), 8) +
      ' ' +
      padR(cnt(s, 'moderate'), 4) +
      ' ' +
      padR(cnt(s, 'minor'), 6) +
      '  ' +
      (s.reached_login ? 'LOGIN' : 'OK')
  )
}
const total = all.reduce((a, s) => a + s.violations, 0)
lines.push('-------------------- -----  ----  -------  ---  -----  ----')
lines.push(`TOTAL                ${padR(total, 5)}`)
lines.push('')
const table = lines.join('\n')
console.log(table)
writeFileSync(pResolve(AUDIT_DIR, '_baseline_table.txt'), table)
console.log(`\nSaved: ${AUDIT_DIR}\\_baseline_table.txt + 7 per-route JSON`)
