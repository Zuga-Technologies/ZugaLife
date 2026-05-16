# ZugaLife WCAG 2.1 AA Audit — 2026-05-16

**Issue:** [Zuga-Technologies/ZugaLife#3](https://github.com/Zuga-Technologies/ZugaLife/issues/3) row T12
**Auditor:** Claude (Opus 4.7) under Buga supervision
**Tool:** `@axe-core/playwright` v4.10, Playwright Chromium, headless
**Target:** `https://zugabot.ai/life` — production, authenticated session
**Scope:** All 7 ZugaLife in-page tabs (URL routes don't exist — tabs are
in-page state controlled by `activeTab` ref in `LifeView.vue`)

## Result

```
BEFORE  →  AFTER

TAB              VIOLS  CRIT  SERIOUS         VIOLS  CRIT  SERIOUS
---------------- -----  ----  -------         -----  ----  -------
dashboard          2     1      1               0     0     0
journal            2     1      1               0     0     0
habits             2     1      1               0     0     0
meditate           2     1      1               0     0     0
therapist          3     2      1               0     0     0
goals              2     1      1               0     0     0
settings           2     1      1               0     0     0
---------------- -----  ----  -------         -----  ----  -------
TOTAL             15     8      7               0     0     0
```

15 → 0 violations across the full ZugaLife user surface.

## Method

1. Login once via Playwright (`.audit/creds.env`, gitignored).
2. Persist auth state to `.audit/storage-state.json` (gitignored).
3. Navigate to `/life` (mobile viewport 414×896 for BottomNavRail), click
   each tab via `button[aria-label="<TabName>"]`. Goals reached via
   dashboard card on desktop viewport. Settings via custom event
   `zugalife-open-settings`.
4. Run axe-core with tags `wcag2a, wcag2aa, wcag21a, wcag21aa` per tab.
5. Fix-verification simulated changes via `page.addStyleTag` and DOM
   patches against prod HTML so we could prove the fixes pass before
   deploy.

All contrast ratios verified with a deterministic WCAG luminance script
(`.audit/wcag/scan-tabs.mjs` includes the verification approach) — not
AI eyeballing.

## Fixes shipped (3 PRs, 2 already pushed)

### ZugaCore — `compliance/wcag-aa-issue3-t12`
- `frontend/theme/theme-vars.css`: `--txt-muted: 82 82 82 → 148 163 184`
  (slate-400). Was 2.45:1 on `--surface-0`, now 7.72:1. Removes ~10
  contrast nodes per ZugaLife tab.

### ZugaApp — `compliance/wcag-aa-issue3-t12`
- `src/components/TopNav.vue`:
  - `.brand-name` color → `#a3e635` (brand lime). Was 1.1:1 on dark chrome
    (slate-900 on near-black — the "Zugabot" wordmark was effectively
    invisible). Now 13.13:1.
  - `.nav-btn`, `.user-btn` color → `#cbd5e1` (slate-300), hover `#f1f5f9`.
    Was 1.86–1.91:1, now 13.33:1.
  - `.user-btn` `aria-label`, `aria-expanded`, `aria-haspopup="menu"`
    (mobile viewport hides `.user-name` so button was unlabeled).
- `src/App.vue`:
  - `.chat-fab` `aria-label="Open Zugabot chat"` + `title`. Icon-only
    button was previously unreachable to screen readers.
- `src/components/ChatPanel.vue`:
  - `.tagline-react-btn` color `#777 → #888888`. Was 4.27:1, now 5.40:1.
  - `.file-input-hidden` `aria-label="Attach image files"`.

### ZugaLife — `compliance/wcag-aa-audit-issue3-t12` (this branch)
- `frontend/tabs/MeditateTab.vue`: removed `opacity-70` from four
  `text-xs` descriptor spans (length-option subs + voice-preset subs).
  Opacity stacked on muted color produced 4.21:1 / 4.03:1 — sub-AA.
  Removing opacity restores 1.0 effective alpha, contrast passes.
- `core` submodule bumped to `10f6e4b` (ZugaCore WCAG fix).
- This report.

## Out of scope (recommended follow-ups)

- **Phase 4 manual keyboard-only sweep** not executed in this session.
  axe automates ~50% of WCAG. Recommended: tab through onboarding,
  each tab's primary action, Esc on every modal, NVDA pass on consent
  gate. File as follow-up issue.
- Goals reach path required overlay removal hack — the `BreathColdOpen`
  welcome overlay captures pointer events and blocks dashboard card
  clicks. Cosmetic, not a11y, but worth tracking.
- Mystical + Biblical theme presets in `theme-vars.css` also define
  `--txt-muted` with sub-AA values (90 80 65 / 100 88 70). Out of
  scope today (those themes aren't active on `/life`).

## Evidence

- `.audit/wcag/scan-tabs.mjs` — primary scanner
- `.audit/wcag/tab-*-baseline-tabs.json` — baseline per-tab axe results
- `.audit/wcag/tab-*-with-fixes.json` — post-fix per-tab axe results
- `.audit/wcag/_baseline_tabs_table.txt` + `_post-fix_tabs_table.txt`

## Definition of Done (per metaprompt)

- [x] ZugaCore + ZugaApp + ZugaLife branches cut and committed
- [x] All 7 primary surfaces re-scanned, **0 AA violations**
- [x] Final report (this file)
- [ ] Mirrored to BugaVault `references/` — deferred (manual sync)
- [ ] Issue #3 comment with before/after — deferred (operator action)
- [x] Per-cluster commits (3 commits across 3 repos, not one bundle)
- [ ] Phase 4 manual keyboard sweep — not run this session
