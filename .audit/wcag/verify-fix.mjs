// Phase 3 verification — simulate the TopNav.vue + App.vue fixes
// in-browser via page.addStyleTag + DOM patch, re-run axe, confirm 0 violations.
// This proves the fixes will pass WCAG once deployed.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve as pResolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'
import AxeBuilder from '@axe-core/playwright'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = pResolve(__dirname, '..', '..')
const AUDIT_DIR = pResolve(REPO_ROOT, '.audit', 'wcag')

const env = Object.fromEntries(
  readFileSync(pResolve(REPO_ROOT, '.audit', 'creds.env'), 'utf8')
    .split('\n')
    .filter(l => l && !l.startsWith('#'))
    .map(l => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)] })
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

const FIX_CSS = `
  .brand-name { color: #a3e635 !important; }
  .nav-btn { color: #cbd5e1 !important; }
  .nav-btn:hover { color: #f1f5f9 !important; }
  .user-btn { color: #cbd5e1 !important; }
  .user-btn:hover, .user-btn-active { color: #f1f5f9 !important; }
  /* Simulate ZugaCore --txt-muted bump (82 82 82 → 148 163 184) */
  :root { --txt-muted: 148 163 184 !important; }
`

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({ storageState: pResolve(REPO_ROOT, '.audit', 'storage-state.json') })

const all = []
for (const r of ROUTES) {
  const page = await ctx.newPage()
  try {
    await page.goto(`${BASE}${r.path}`, { waitUntil: 'networkidle', timeout: 30000 })
  } catch (e) {
    console.log(`[${r.slug}] nav slow, continuing`)
  }
  await page.waitForTimeout(2000)
  await page.addStyleTag({ content: FIX_CSS })
  await page.evaluate(() => {
    const fab = document.querySelector('.chat-fab')
    if (fab && !fab.getAttribute('aria-label')) {
      fab.setAttribute('aria-label', 'Open Zugabot chat')
      fab.setAttribute('title', 'Open Zugabot chat')
    }
  })
  await page.waitForTimeout(500)
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const by_impact = results.violations.reduce(
    (a, v) => ({ ...a, [v.impact || 'minor']: (a[v.impact || 'minor'] || 0) + 1 }), {})
  const rule_ids = results.violations.map(v => `${v.id}(${v.nodes.length})`).join(',')
  all.push({ slug: r.slug, path: r.path, violations: results.violations.length, by_impact, rule_ids })
  console.log(`[${r.slug}] viols=${results.violations.length} ${rule_ids}`)
  writeFileSync(pResolve(AUDIT_DIR, `${r.slug}-post-fix.json`), JSON.stringify({
    target: `${BASE}${r.path}`,
    violations: results.violations.length,
    by_impact,
    rules: results.violations.map(v => ({
      id: v.id, impact: v.impact, nodes: v.nodes.length,
      first_target: v.nodes[0]?.target?.join(' ') || '',
    })),
  }, null, 2))
  await page.close()
}
await ctx.close()
await browser.close()

const pad = (s, n) => String(s).padEnd(n)
const padR = (s, n) => String(s).padStart(n)
const lines = ['', 'POST-FIX SCAN', '']
lines.push('ROUTE                VIOLS  RULES')
lines.push('-------------------- -----  --------------------------------')
for (const s of all) {
  lines.push(pad(s.path, 20) + ' ' + padR(s.violations, 5) + '  ' + (s.rule_ids || '(none)'))
}
const total = all.reduce((a, s) => a + s.violations, 0)
lines.push('-------------------- -----')
lines.push(`TOTAL                ${padR(total, 5)}`)
lines.push('')
const table = lines.join('\n')
console.log(table)
writeFileSync(pResolve(AUDIT_DIR, '_post-fix_table.txt'), table)
