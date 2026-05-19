// Deterministic WCAG 2.1 contrast for theme presets.
// Per feedback_verify_ai_quantitative_claims — never eyeball.
const lum = ([r, g, b]) => {
  const c = (x) => {
    x = x / 255
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * c(r) + 0.7152 * c(g) + 0.0722 * c(b)
}
const ratio = (a, b) => {
  const la = lum(a), lb = lum(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}
const hex = ([r, g, b]) => '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
const fmt = (r) => r.toFixed(2)

const cases = [
  // name, fg, bg, current?
  { theme: 'tarot/mystical', surface0: [13, 10, 26], muted: [90, 80, 65], secondary: [170, 160, 140] },
  { theme: 'biblical',       surface0: [26, 21, 16], muted: [100, 88, 70], secondary: [180, 165, 140] },
  { theme: ':root/default',  surface0: [10, 10, 10], muted: [148, 163, 184], secondary: [163, 163, 163] },
]

console.log('THEME            SURFACE0   MUTED-FG    RATIO   AA?  SECONDARY-FG  RATIO  AA?')
console.log('---------------- ---------- ----------  ------  ---  -----------   ------ ---')
for (const c of cases) {
  const rm = ratio(c.muted, c.surface0)
  const rs = ratio(c.secondary, c.surface0)
  const pad = (s, n) => String(s).padEnd(n)
  console.log(
    pad(c.theme, 16), ' ', pad(hex(c.surface0), 9), pad(hex(c.muted), 10),
    ' ', fmt(rm).padStart(5), ' ', (rm >= 4.5 ? 'YES' : 'NO ').padEnd(3),
    pad(hex(c.secondary), 12), fmt(rs).padStart(5), ' ', (rs >= 4.5 ? 'YES' : 'NO ')
  )
}

// Now search for AA-passing replacements that respect each theme's palette.
console.log('\nCANDIDATE REPLACEMENTS (keep theme hue, raise lightness until AA passes)')
console.log('THEME            TRY HSL/RGB                       RATIO  AA?')
console.log('---------------- --------------------------------- ------ ---')

// Mystical: parchment/aged-gold-cream — RGB direction = warmer cream
const mysticalCands = [
  [140, 130, 115], [155, 145, 128], [170, 160, 140], [180, 170, 150], [195, 183, 160],
]
for (const m of mysticalCands) {
  const r = ratio(m, [13, 10, 26])
  console.log('mystical         ', `${hex(m).padEnd(9)} (${m.join(' ').padEnd(16)})  `, fmt(r).padStart(5), ' ', r >= 4.5 ? 'YES' : 'NO')
}

// Biblical: parchment scroll — RGB direction = warmer beige
const biblicalCands = [
  [140, 125, 105], [155, 140, 118], [170, 155, 130], [180, 165, 140], [195, 178, 150],
]
for (const m of biblicalCands) {
  const r = ratio(m, [26, 21, 16])
  console.log('biblical         ', `${hex(m).padEnd(9)} (${m.join(' ').padEnd(16)})  `, fmt(r).padStart(5), ' ', r >= 4.5 ? 'YES' : 'NO')
}
