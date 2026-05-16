// Tab-aware scanner — clicks ZugaLife in-page tabs via BottomNavRail
// (mobile viewport) and runs axe against each tab state.
// Goals/Settings reached via dashboard cards or user menu — best effort.
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

const FIX_CSS = `
  .brand-name { color: #a3e635 !important; }
  .nav-btn { color: #cbd5e1 !important; }
  .nav-btn:hover { color: #f1f5f9 !important; }
  .user-btn { color: #cbd5e1 !important; }
  .user-btn:hover, .user-btn-active { color: #f1f5f9 !important; }
  :root { --txt-muted: 148 163 184 !important; }
  /* Sim: MeditateTab opacity-70 removed (matches all 4 source occurrences) */
  button .text-xs[class*="opacity-70"],
  button .text-xs.opacity-70,
  span.opacity-70.text-xs,
  .text-xs.opacity-70 { opacity: 1 !important; }
  /* Sim: ChatPanel tagline-react-btn color bump (#777 → #888888) */
  .tagline-react-btn { color: #888888 !important; }
`

const APPLY_FIX = process.argv.includes('--with-fixes')

const browser = await chromium.launch({ headless: true })
const ctx = await browser.newContext({
  storageState: pResolve(REPO_ROOT, '.audit', 'storage-state.json'),
  viewport: { width: 414, height: 896 },
})
const page = await ctx.newPage()

async function applyFixes() {
  if (!APPLY_FIX) return
  await page.addStyleTag({ content: FIX_CSS })
  await page.evaluate(() => {
    const fab = document.querySelector('.chat-fab')
    if (fab && !fab.getAttribute('aria-label')) {
      fab.setAttribute('aria-label', 'Open Zugabot chat')
      fab.setAttribute('title', 'Open Zugabot chat')
    }
    const userBtn = document.querySelector('.user-btn')
    if (userBtn && !userBtn.getAttribute('aria-label')) {
      userBtn.setAttribute('aria-label', 'User menu')
      userBtn.setAttribute('aria-haspopup', 'menu')
    }
    const fileInput = document.querySelector('.file-input-hidden')
    if (fileInput && !fileInput.getAttribute('aria-label')) {
      fileInput.setAttribute('aria-label', 'Attach image files')
    }
  })
  await page.waitForTimeout(300)
}

async function scan(slug) {
  await applyFixes()
  const r = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const by_impact = r.violations.reduce(
    (a, v) => ({ ...a, [v.impact || 'minor']: (a[v.impact || 'minor'] || 0) + 1 }), {})
  const summary = {
    slug,
    final_url: page.url(),
    violations: r.violations.length,
    by_impact,
    rules: r.violations.map(v => ({
      id: v.id, impact: v.impact, nodes: v.nodes.length,
      first_target: v.nodes[0]?.target?.join(' ') || '',
    })),
    nodes_detail: r.violations.flatMap(v => v.nodes.map(n => ({
      rule: v.id, impact: v.impact,
      target: n.target.join(' '),
      summary: (n.failureSummary || '').replace(/\n/g, ' | ').slice(0, 220),
      html: n.html.slice(0, 180),
    }))),
  }
  const suffix = APPLY_FIX ? '-with-fixes' : '-baseline-tabs'
  writeFileSync(pResolve(AUDIT_DIR, `${slug}${suffix}.json`), JSON.stringify(summary, null, 2))
  return summary
}

async function clickTab(label) {
  // BottomNavRail buttons have explicit aria-label. Force click in case
  // an overlay covers part of the button — we just want the click handler.
  const btn = page.locator(`button[aria-label="${label}"]`).first()
  await btn.waitFor({ state: 'attached', timeout: 8000 })
  await btn.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {})
  await btn.click({ force: true, timeout: 8000 })
  await page.waitForTimeout(1500)
}

// Start on /life dashboard
await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)
// Close any onboarding/breath-open overlay if present
const closeBtn = page.locator('button[aria-label="Close"], .breath-open button').first()
if (await closeBtn.isVisible().catch(() => false)) {
  await closeBtn.click().catch(() => {})
  await page.waitForTimeout(800)
}

const TABS = [
  { slug: 'tab-dashboard', label: null }, // already there
  { slug: 'tab-journal', label: 'Journal' },
  { slug: 'tab-habits', label: 'Habits' },
  { slug: 'tab-meditate', label: 'Meditate' },
  { slug: 'tab-therapist', label: 'Companion' },
]

const all = []
for (const t of TABS) {
  if (t.label) {
    try {
      await clickTab(t.label)
    } catch (e) {
      console.log(`[${t.slug}] click failed: ${e.message.split('\n')[0]}`)
      continue
    }
  }
  const s = await scan(t.slug)
  all.push(s)
  console.log(`[${t.slug}]  ${s.violations} viols  ${JSON.stringify(s.by_impact)}`)
}

// Goals — reach via dashboard "Goals" card (desktop viewport so grid renders)
try {
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.waitForTimeout(800)
  // Re-navigate to /life to get a clean dashboard with the goals card.
  await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(2500)
  // Dismiss any breath-open overlay (it captures pointer events).
  await page.evaluate(() => {
    document.querySelectorAll('.breath-open, [class*="cold-open"], [class*="welcome-overlay"]').forEach(el => el.remove())
  })
  await page.waitForTimeout(400)
  const goalsCard = page.locator('button.dash-card:has-text("Goals")').first()
  await goalsCard.click({ force: true, timeout: 8000 })
  await page.waitForTimeout(1500)
  const s = await scan('tab-goals')
  all.push(s)
  console.log(`[tab-goals]  ${s.violations} viols  ${JSON.stringify(s.by_impact)}`)
} catch (e) {
  console.log('[tab-goals] err:', e.message.split('\n')[0])
}

// Settings — ZugaLife dispatches `zugalife-open-settings` custom event to
// reveal SettingsPanel. No URL or button on prod chrome — event is the door.
try {
  await page.evaluate(() => {
    document.dispatchEvent(new CustomEvent('zugalife-open-settings'))
  })
  await page.waitForTimeout(1500)
  const s = await scan('tab-settings')
  all.push(s)
  console.log(`[tab-settings]  ${s.violations} viols  ${JSON.stringify(s.by_impact)}`)
} catch (e) {
  console.log('[tab-settings] err:', e.message.split('\n')[0])
}

await ctx.close()
await browser.close()

const pad = (s, n) => String(s).padEnd(n)
const padR = (s, n) => String(s).padStart(n)
const cnt = (s, k) => s.by_impact?.[k] || 0
const lines = ['', `${APPLY_FIX ? 'POST-FIX' : 'BASELINE'} TABS SCAN`, '']
lines.push('TAB              VIOLS  CRIT  SERIOUS  MOD  MINOR  URL')
lines.push('---------------- -----  ----  -------  ---  -----  --------------------')
for (const s of all) {
  lines.push(
    pad(s.slug, 16) + ' ' + padR(s.violations, 5) + ' ' + padR(cnt(s, 'critical'), 5) +
    ' ' + padR(cnt(s, 'serious'), 8) + ' ' + padR(cnt(s, 'moderate'), 4) +
    ' ' + padR(cnt(s, 'minor'), 6) + '  ' + s.final_url.replace(BASE, '')
  )
}
const total = all.reduce((a, s) => a + s.violations, 0)
lines.push('---------------- -----  ----  -------  ---  -----')
lines.push(`TOTAL            ${padR(total, 5)}`)
lines.push('')
const table = lines.join('\n')
console.log(table)
const tableFile = APPLY_FIX ? '_post-fix_tabs_table.txt' : '_baseline_tabs_table.txt'
writeFileSync(pResolve(AUDIT_DIR, tableFile), table)
