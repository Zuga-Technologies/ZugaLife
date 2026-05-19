// Phase 2.1 — Programmatic keyboard sweep.
// For each tab + critical modal:
//   - Walk N Tabs from body, record focused element
//   - Detect traps (same element repeats), missing focus, hidden focus
//   - For modals: open via keyboard, Esc closes, focus returns
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve as pResolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

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

async function focusedDescriptor() {
  return await page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return null
    // Check focus visibility — does the browser show a focus ring?
    // We use a pragma: getComputedStyle outline-width OR box-shadow.
    const cs = getComputedStyle(el)
    const hasOutline = cs.outlineStyle !== 'none' && cs.outlineWidth !== '0px'
    const hasBoxShadow = cs.boxShadow !== 'none'
    const ringVisible = hasOutline || hasBoxShadow
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      cls: (el.className || '').toString().slice(0, 50),
      label: el.getAttribute('aria-label') || el.textContent?.slice(0, 40).trim() || '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      ringVisible,
    }
  })
}

async function walkTabs(label, n = 15) {
  // Reset focus to body before walking
  await page.evaluate(() => document.body.focus())
  await page.locator('body').click({ position: { x: 0, y: 0 }, force: true }).catch(() => {})
  const focused = []
  for (let i = 0; i < n; i++) {
    await page.keyboard.press('Tab')
    await page.waitForTimeout(60)
    const d = await focusedDescriptor()
    focused.push(d)
  }
  return { label, focused }
}

const results = { tabs: [], modals: [] }

// Login state
await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)
const closeBtn = page.locator('button[aria-label="Close"], .breath-open button').first()
if (await closeBtn.isVisible().catch(() => false)) {
  await closeBtn.click().catch(() => {})
  await page.waitForTimeout(800)
}

// Tab sweep: dashboard + Journal + Habits + Meditate + Companion (mobile viewport)
const TABS_MOBILE = [
  { slug: 'tab-dashboard', label: null },
  { slug: 'tab-journal', label: 'Journal' },
  { slug: 'tab-habits', label: 'Habits' },
  { slug: 'tab-meditate', label: 'Meditate' },
  { slug: 'tab-therapist', label: 'Companion' },
]
for (const t of TABS_MOBILE) {
  if (t.label) {
    const btn = page.locator(`button[aria-label="${t.label}"]`).first()
    await btn.click({ force: true, timeout: 8000 }).catch(() => {})
    await page.waitForTimeout(1500)
  }
  const r = await walkTabs(t.slug)
  results.tabs.push(r)
  // Brief
  const trap = (() => {
    const seen = {}
    for (const f of r.focused) {
      const k = f ? `${f.tag}.${f.cls}` : '<body>'
      seen[k] = (seen[k] || 0) + 1
      if (seen[k] >= 4) return k
    }
    return null
  })()
  const noRing = r.focused.filter(f => f && f.visible && !f.ringVisible).length
  console.log(`[${t.slug}] focusable=${r.focused.filter(f=>f).length}/15 trap=${trap||'-'} no-ring=${noRing}`)
}

// Desktop viewport for Goals + Settings
await page.setViewportSize({ width: 1280, height: 900 })
await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
await page.waitForTimeout(2500)
await page.evaluate(() => {
  document.querySelectorAll('.breath-open, [class*="cold-open"], [class*="welcome-overlay"]').forEach(el => el.remove())
})

// Goals — keyboard nav to dashboard card
try {
  await page.locator('button.dash-card:has-text("Goals")').first().focus()
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1500)
  const r = await walkTabs('tab-goals')
  results.tabs.push(r)
  console.log(`[tab-goals] focusable=${r.focused.filter(f=>f).length}/15`)
} catch (e) { console.log('[tab-goals] err:', e.message.split('\n')[0]) }

// Settings panel — Esc-to-close test
try {
  await page.evaluate(() => { document.dispatchEvent(new CustomEvent('zugalife-open-settings')) })
  await page.waitForTimeout(1500)
  const r = await walkTabs('tab-settings')
  results.tabs.push(r)
  console.log(`[tab-settings] focusable=${r.focused.filter(f=>f).length}/15`)

  // Esc should close the settings panel.
  await page.keyboard.press('Escape')
  await page.waitForTimeout(800)
  const stillOpen = await page.locator('[class*="settings"]:visible, [class*="SettingsPanel"]:visible').count()
  results.modals.push({ name: 'SettingsPanel', escCloses: stillOpen === 0, stillOpenCount: stillOpen })
  console.log(`[modal SettingsPanel] esc-closes=${stillOpen === 0}`)
} catch (e) { console.log('[tab-settings] err:', e.message.split('\n')[0]) }

// FAB chat open/close via keyboard
try {
  await page.setViewportSize({ width: 414, height: 896 })
  await page.goto(`${BASE}/life`, { waitUntil: 'networkidle', timeout: 30000 })
  await page.waitForTimeout(2500)
  const fab = page.locator('.chat-fab').first()
  await fab.focus()
  await page.keyboard.press('Enter')
  await page.waitForTimeout(800)
  const chatOpen = await page.locator('.chat-window:visible').count()
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)
  const chatStillOpen = await page.locator('.chat-window:visible').count()
  results.modals.push({
    name: 'ChatWindow',
    opensViaKeyboard: chatOpen > 0,
    escCloses: chatOpen > 0 && chatStillOpen === 0,
  })
  console.log(`[modal ChatWindow] open-via-keyboard=${chatOpen > 0} esc-closes=${chatOpen > 0 && chatStillOpen === 0}`)
} catch (e) { console.log('[modal ChatWindow] err:', e.message.split('\n')[0]) }

await ctx.close()
await browser.close()

writeFileSync(pResolve(AUDIT_DIR, '_keyboard_sweep.json'), JSON.stringify(results, null, 2))

// ASCII table
const pad = (s, n) => String(s).padEnd(n)
const padR = (s, n) => String(s).padStart(n)
console.log('\nKEYBOARD SWEEP — Phase 2.1')
console.log('SURFACE          FOCUSABLE  TRAP?  NO-RING')
console.log('---------------- ---------  -----  -------')
for (const t of results.tabs) {
  const n = t.focused.filter(f => f).length
  const noRing = t.focused.filter(f => f && f.visible && !f.ringVisible).length
  const seen = {}
  let trap = '-'
  for (const f of t.focused) { const k = f ? `${f.tag}.${f.cls}` : '<body>'; seen[k] = (seen[k] || 0) + 1; if (seen[k] >= 4) { trap = k.slice(0, 12); break } }
  console.log(pad(t.label, 16), padR(`${n}/15`, 9), '  ', pad(trap, 5), '  ', padR(noRing, 6))
}
console.log('\nMODAL TESTS')
for (const m of results.modals) {
  console.log(JSON.stringify(m))
}
