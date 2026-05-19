// Phase 2 — Extended scan: WCAG AA + best-practice rules that catch
// label semantics, heading-order, landmark-one-main, skip-link, region.
// Reuses storage-state.json from Phase 1 login.mjs.
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
    .split('\n').filter(l => l && !l.startsWith('#'))
    .map(l => { const i = l.indexOf('='); return [l.slice(0, i), l.slice(i + 1)] })
)
const BASE = env.AUDIT_BASE_URL || 'https://zugabot.ai'

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({
  storageState: pResolve(REPO_ROOT, '.audit', 'storage-state.json'),
  viewport: { width: 414, height: 896 },
})
const page = await ctx.newPage()

async function scan(slug) {
  const r = await new AxeBuilder({ page })
    // wcag2aa + AAA + best-practice catches: label, heading-order,
    // landmark-one-main, region, skip-link, page-has-heading-one.
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
    .analyze()
  const rules = r.violations.map(v => ({
    id: v.id, impact: v.impact, nodes: v.nodes.length,
    first_target: v.nodes[0]?.target?.join(' ') || '',
    first_html: v.nodes[0]?.html?.slice(0, 160) || '',
  }))
  const summary = { slug, url: page.url(), violations: r.violations.length, rules }
  writeFileSync(pResolve(AUDIT_DIR, `${slug}-phase2-extended.json`), JSON.stringify(summary, null, 2))
  return summary
}

async function clickTab(label) {
  const btn = page.locator(`button[aria-label="${label}"]`).first()
  await btn.waitFor({ state: 'attached', timeout: 8000 })
  await btn.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
  await btn.click({ force: true, timeout: 8000 })
  await page.waitForTimeout(1500)
}

await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)
const closeBtn = page.locator('button[aria-label="Close"], .breath-open button').first()
if (await closeBtn.isVisible().catch(() => false)) {
  await closeBtn.click().catch(() => {})
  await page.waitForTimeout(800)
}

const TABS = [
  { slug: 'tab-dashboard', label: null },
  { slug: 'tab-journal', label: 'Journal' },
  { slug: 'tab-habits', label: 'Habits' },
  { slug: 'tab-meditate', label: 'Meditate' },
  { slug: 'tab-therapist', label: 'Companion' },
]

const all = []
for (const t of TABS) {
  if (t.label) {
    try { await clickTab(t.label) } catch (e) { console.log(`[${t.slug}] click failed`); continue }
  }
  const s = await scan(t.slug)
  all.push(s)
  console.log(`[${t.slug}] viols=${s.violations}`)
  for (const r of s.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n) ${r.first_target.slice(0, 80)}`)
}

// Goals
try {
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.waitForTimeout(800)
  await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(2500)
  await page.evaluate(() => {
    document.querySelectorAll('.breath-open, [class*="cold-open"], [class*="welcome-overlay"]').forEach(el => el.remove())
  })
  await page.waitForTimeout(400)
  const goalsCard = page.locator('button.dash-card:has-text("Goals")').first()
  await goalsCard.click({ force: true, timeout: 8000 })
  await page.waitForTimeout(1500)
  const s = await scan('tab-goals')
  all.push(s)
  console.log(`[tab-goals] viols=${s.violations}`)
  for (const r of s.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n) ${r.first_target.slice(0, 80)}`)
} catch (e) { console.log('[tab-goals] err:', e.message.split('\n')[0]) }

// Settings
try {
  await page.evaluate(() => { document.dispatchEvent(new CustomEvent('zugalife-open-settings')) })
  await page.waitForTimeout(1500)
  const s = await scan('tab-settings')
  all.push(s)
  console.log(`[tab-settings] viols=${s.violations}`)
  for (const r of s.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n) ${r.first_target.slice(0, 80)}`)
} catch (e) { console.log('[tab-settings] err:', e.message.split('\n')[0]) }

await ctx.close()
await browser.close()

const total = all.reduce((a, s) => a + s.violations, 0)
console.log(`\nTOTAL ${total} violations across ${all.length} surfaces`)
