/**
 * ZugaLife Theme Preset Registry
 *
 * Each preset maps to a [data-theme="..."] block in theme-vars.css.
 * The preset metadata here drives the UI picker and marketplace publishing.
 *
 * To add a new preset:
 * 1. Add CSS vars in ZugaCore/frontend/theme/theme-vars.css under [data-theme="your-id"]
 * 2. Add a PresetDefinition here
 * 3. (Optional) Add mood overrides in mood-presets.ts
 */

export interface PresetDefinition {
  id: string
  name: string
  description: string
  /** CSS gradient for the preview swatch in the picker */
  preview: string
  /** Google Font to load (if not Inter) */
  googleFont?: string
  /** Category for marketplace filtering */
  category: 'default' | 'spiritual' | 'aesthetic' | 'minimal' | 'custom'
}

export const THEME_PRESETS: PresetDefinition[] = [
  {
    id: 'default',
    name: 'Rose Coral',
    description: 'Rose coral & dark — holistic zen, the ZugaLife studio identity',
    preview: 'linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 50%, #fb7185 100%)',
    category: 'default',
  },
  {
    id: 'tarot',
    name: 'Tarot',
    description: 'Mystic gold & deep indigo — for the spiritually inclined',
    preview: 'linear-gradient(135deg, #0d0a1a 0%, #1c1632 50%, #c4a747 100%)',
    googleFont: 'Cinzel',
    category: 'spiritual',
  },
  {
    id: 'biblical',
    name: 'Devotional',
    description: 'Warm parchment tones & classic serif — scripture & prayer',
    preview: 'linear-gradient(135deg, #1a1510 0%, #2c1c12 50%, #8b6914 100%)',
    googleFont: 'EB+Garamond',
    category: 'spiritual',
  },
]

/** Look up a preset by ID, falling back to default */
export function getPreset(id: string): PresetDefinition {
  return THEME_PRESETS.find(p => p.id === id) || THEME_PRESETS[0]
}

/** Apply a theme preset to the document. Sets data-theme and loads fonts. */
export function applyPreset(id: string): void {
  const preset = getPreset(id)

  // 'default' = the ZugaLife studio identity (data-theme="life", rose coral accent).
  // Other presets override accent/surface/typography on top of the same ZugaCore base.
  document.documentElement.setAttribute(
    'data-theme',
    id === 'default' ? 'life' : id,
  )

  // Load Google Font if needed
  if (preset.googleFont) {
    loadGoogleFont(preset.googleFont)
  }
}

/** Get the currently active preset ID from the DOM */
export function getActivePresetId(): string {
  const attr = document.documentElement.getAttribute('data-theme')
  // 'life' is the studio identity exposed to users as 'default'.
  if (!attr || attr === 'life') return 'default'
  return attr
}

// --- Internal ---

const loadedFonts = new Set<string>()

function loadGoogleFont(font: string): void {
  if (loadedFonts.has(font)) return
  loadedFonts.add(font)

  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?family=${font}:wght@400;600;700&display=swap`
  document.head.appendChild(link)
}
