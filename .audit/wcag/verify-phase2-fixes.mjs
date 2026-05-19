// Simulate Phase 2 fixes against prod DOM and prove they clear the
// extended axe scan. Mirrors Phase 1's verify-fix pattern.
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

async function applyPhase2Patches() {
  await page.evaluate(() => {
    // Fix 1: TopNav brand-mark alt → empty (decorative; .brand-name labels it)
    document.querySelectorAll('img.brand-mark').forEach(img => img.setAttribute('alt', ''))
    document.querySelectorAll('a.brand').forEach(a => a.setAttribute('aria-label', 'Zugabot home'))
    // Fix 2: chat-window gets role+aria-label so .chat-* contents are in a landmark
    const cw = document.querySelector('.chat-window')
    if (cw) {
      cw.setAttribute('role', 'region')
      cw.setAttribute('aria-label', 'Zugabot chat')
    }
  })
  await page.waitForTimeout(300)
}

async function scan(slug) {
  await applyPhase2Patches()
  const r = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'])
    .analyze()
  const rules = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }))
  writeFileSync(pResolve(AUDIT_DIR, `${slug}-phase2-post-fix.json`),
    JSON.stringify({ slug, url: page.url(), violations: r.violations.length, rules }, null, 2))
  return { slug, violations: r.violations.length, rules }
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

// Open the chat window so chat-title is in DOM for therapist scan.
const fab = page.locator('.chat-fab').first()
if (await fab.isVisible().catch(() => false)) {
  await fab.click().catch(() => {})
  await page.waitForTimeout(800)
  // Close it again so subsequent tabs don't have chat overlay
  const close = page.locator('.chat-close').first()
  if (await close.isVisible().catch(() => false)) {
    await close.click().catch(() => {})
    await page.waitForTimeout(500)
  }
}

const all = []
for (const t of [
  { slug: 'tab-dashboard', label: null },
  { slug: 'tab-therapist', label: 'Companion' },
]) {
  if (t.label) { try { await clickTab(t.label) } catch (e) { continue } }
  // For therapist, open chat panel (it's a Companion chat, different from FAB).
  const s = await scan(t.slug)
  all.push(s)
  console.log(`[${t.slug}] viols=${s.violations}`)
  for (const r of s.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n)`)
}

// Goals + settings (desktop viewport)
await page.setViewportSize({ width: 1280, height: 900 })
await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)
await page.evaluate(() => {
  document.querySelectorAll('.breath-open, [class*="cold-open"], [class*="welcome-overlay"]').forEach(el => el.remove())
})

const goalsCard = page.locator('button.dash-card:has-text("Goals")').first()
await goalsCard.click({ force: true, timeout: 8000 }).catch(() => {})
await page.waitForTimeout(1500)
const sg = await scan('tab-goals')
all.push(sg)
console.log(`[tab-goals] viols=${sg.violations}`)
for (const r of sg.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n)`)

await page.evaluate(() => { document.dispatchEvent(new CustomEvent('zugalife-open-settings')) })
await page.waitForTimeout(1500)
const ss = await scan('tab-settings')
all.push(ss)
console.log(`[tab-settings] viols=${ss.violations}`)
for (const r of ss.rules) console.log(`   ${r.id} (${r.impact}, ${r.nodes}n)`)

await ctx.close()
await browser.close()

const total = all.reduce((a, s) => a + s.violations, 0)
console.log(`\nPOST-PHASE-2-FIX TOTAL: ${total} violations`)
