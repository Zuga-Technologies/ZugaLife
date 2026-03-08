/**
 * Background theme definitions — video-first with canvas fallback.
 *
 * Video files go in public/backgrounds/ as MP4.
 * Themes persist in localStorage under 'zugalife-bg-theme'.
 */

export type ThemeId =
  | 'none'
  | 'northern-lights'
  | 'still-water'
  | 'cosmic-drift'
  | 'rainy-window'
  | 'forest-stream'
  | 'campfire'
  | 'golden-sunset'
  | 'misty-forest'
  | 'soft-bokeh'
  | 'custom'

export interface ThemeDefinition {
  id: ThemeId
  name: string
  description: string
  preview: string
  video?: string        // path under /backgrounds/
  overlay?: number      // dark overlay opacity (0-1) for bright videos
  fallbackBg?: string   // CSS gradient fallback while video loads
  speed?: number        // playback rate (default 0.6) — lower = slower
}

export const THEMES: ThemeDefinition[] = [
  {
    id: 'none',
    name: 'Default Dark',
    description: 'Clean dark background — no animation',
    preview: 'linear-gradient(135deg, #0a0a0a, #1a1a1a)',
  },
  {
    id: 'northern-lights',
    name: 'Northern Lights',
    description: 'Real aurora borealis timelapse',
    preview: 'linear-gradient(135deg, #0f172a, #2dd4bf, #8b5cf6)',
    video: '/backgrounds/northern-lights.mp4',
    overlay: 0.15,
    speed: 0.3,   // timelapse — needs heavy slowdown
    fallbackBg: 'linear-gradient(135deg, #0f172a, #1a3a4a)',
  },
  {
    id: 'still-water',
    name: 'Still Water',
    description: 'Gentle ocean surface, soft reflections',
    preview: 'linear-gradient(135deg, #0c4a6e, #0ea5e9, #164e63)',
    video: '/backgrounds/still-water.mp4',
    overlay: 0.3,
    speed: 0.5,   // real-time water — gentle slowdown
    fallbackBg: 'linear-gradient(135deg, #0a1929, #0c4a6e)',
  },
  {
    id: 'cosmic-drift',
    name: 'Cosmic Drift',
    description: 'Stars drifting through deep space',
    preview: 'radial-gradient(ellipse at 30% 40%, #1a1a2e 0%, #090909 100%)',
    video: '/backgrounds/cosmic-drift.mp4',
    overlay: 0,
    speed: 0.4,   // slow star drift
    fallbackBg: 'radial-gradient(ellipse at 30% 40%, #12121e, #060610)',
  },
  {
    id: 'rainy-window',
    name: 'Rainy Window',
    description: 'Raindrops on glass with soft bokeh lights',
    preview: 'linear-gradient(135deg, #1a1a2e, #2d3748, #1a202c)',
    video: '/backgrounds/rainy-window.mp4',
    overlay: 0.1,
    speed: 0.6,   // real-time rain — slight slowdown
    fallbackBg: 'linear-gradient(135deg, #1a1a2e, #2d3748)',
  },
  {
    id: 'forest-stream',
    name: 'Forest Stream',
    description: 'Sunlit stream flowing through the forest',
    preview: 'linear-gradient(135deg, #14532d, #166534, #1a3a1a)',
    video: '/backgrounds/forest-stream.mp4',
    overlay: 0.45,
    speed: 0.5,   // drone footage — moderate slowdown
    fallbackBg: 'linear-gradient(135deg, #0a1a0a, #14532d)',
  },
  {
    id: 'campfire',
    name: 'Campfire',
    description: 'Crackling flames in the dark woods',
    preview: 'linear-gradient(135deg, #1a0a00, #92400e, #451a03)',
    video: '/backgrounds/campfire.mp4',
    overlay: 0.2,
    speed: 0.7,   // real fire — too slow looks unnatural
    fallbackBg: 'linear-gradient(135deg, #1a0a00, #2a1508)',
  },
  {
    id: 'golden-sunset',
    name: 'Golden Sunset',
    description: 'Warm sunset timelapse over rolling hills',
    preview: 'linear-gradient(135deg, #451a03, #d97706, #92400e)',
    video: '/backgrounds/golden-sunset.mp4',
    overlay: 0.4,
    speed: 0.6,   // real-time sailboat sunset
    fallbackBg: 'linear-gradient(135deg, #1a0f05, #451a03)',
  },
  {
    id: 'misty-forest',
    name: 'Misty Forest',
    description: 'Aerial drift through fog-covered trees',
    preview: 'linear-gradient(135deg, #1e293b, #475569, #334155)',
    video: '/backgrounds/misty-forest.mp4',
    overlay: 0.4,
    speed: 0.4,   // aerial drone — slow float
    fallbackBg: 'linear-gradient(135deg, #0f1720, #1e293b)',
  },
  {
    id: 'soft-bokeh',
    name: 'Soft Bokeh',
    description: 'Floating monochrome light orbs',
    preview: 'linear-gradient(135deg, #111, #333, #111)',
    video: '/backgrounds/soft-bokeh.mp4',
    overlay: 0.1,
    speed: 0.5,   // floating orbs — dreamy slowdown
    fallbackBg: 'linear-gradient(135deg, #0a0a0a, #1a1a1a)',
  },
  {
    id: 'custom',
    name: 'Custom',
    description: 'Your own image or video background',
    preview: 'linear-gradient(135deg, #333, #555, #333)',
  },
]

// --- Storage helpers ---

const STORAGE_KEY = 'zugalife-bg-theme'
const CUSTOM_IMG_KEY = 'zugalife-bg-custom-img'
const CUSTOM_OPACITY_KEY = 'zugalife-bg-custom-opacity'

export function getSavedTheme(): ThemeId {
  return (localStorage.getItem(STORAGE_KEY) as ThemeId) || 'northern-lights'
}
export function saveTheme(id: ThemeId) { localStorage.setItem(STORAGE_KEY, id) }
export function getTheme(id: ThemeId): ThemeDefinition {
  return THEMES.find(t => t.id === id) || THEMES[0]
}

export function getCustomImage(): string | null { return localStorage.getItem(CUSTOM_IMG_KEY) }
export function saveCustomImage(dataUrl: string) { localStorage.setItem(CUSTOM_IMG_KEY, dataUrl) }
export function removeCustomImage() { localStorage.removeItem(CUSTOM_IMG_KEY) }
export function getCustomOpacity(): number {
  const val = localStorage.getItem(CUSTOM_OPACITY_KEY)
  return val ? parseFloat(val) : 0.3
}
export function saveCustomOpacity(opacity: number) { localStorage.setItem(CUSTOM_OPACITY_KEY, String(opacity)) }

// --- Custom video (IndexedDB — too large for localStorage) ---

const CUSTOM_VIDEO_SPEED_KEY = 'zugalife-bg-custom-video-speed'
const IDB_NAME = 'zugalife-bg'
const IDB_STORE = 'custom-media'
const IDB_VIDEO_KEY = 'custom-video'

function openIDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1)
    req.onupgradeneeded = () => { req.result.createObjectStore(IDB_STORE) }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function saveCustomVideo(blob: Blob): Promise<void> {
  const db = await openIDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite')
    tx.objectStore(IDB_STORE).put(blob, IDB_VIDEO_KEY)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => { db.close(); reject(tx.error) }
  })
}

export async function getCustomVideo(): Promise<string | null> {
  try {
    const db = await openIDB()
    return new Promise((resolve) => {
      const tx = db.transaction(IDB_STORE, 'readonly')
      const req = tx.objectStore(IDB_STORE).get(IDB_VIDEO_KEY)
      req.onsuccess = () => {
        db.close()
        if (req.result instanceof Blob) {
          resolve(URL.createObjectURL(req.result))
        } else {
          resolve(null)
        }
      }
      req.onerror = () => { db.close(); resolve(null) }
    })
  } catch { return null }
}

export async function removeCustomVideo(): Promise<void> {
  try {
    const db = await openIDB()
    return new Promise((resolve) => {
      const tx = db.transaction(IDB_STORE, 'readwrite')
      tx.objectStore(IDB_STORE).delete(IDB_VIDEO_KEY)
      tx.oncomplete = () => { db.close(); resolve() }
      tx.onerror = () => { db.close(); resolve() }
    })
  } catch { /* ignore */ }
}

export function getCustomVideoSpeed(): number {
  const val = localStorage.getItem(CUSTOM_VIDEO_SPEED_KEY)
  return val ? parseFloat(val) : 0.5
}
export function saveCustomVideoSpeed(speed: number) {
  localStorage.setItem(CUSTOM_VIDEO_SPEED_KEY, String(speed))
}

/** Check what type of custom media is stored */
export function getCustomMediaType(): 'image' | 'video' | null {
  if (localStorage.getItem(CUSTOM_IMG_KEY)) return 'image'
  // Video check is async, so we use a sync flag
  return localStorage.getItem('zugalife-bg-has-custom-video') === '1' ? 'video' : null
}
export function setCustomVideoFlag(has: boolean) {
  if (has) localStorage.setItem('zugalife-bg-has-custom-video', '1')
  else localStorage.removeItem('zugalife-bg-has-custom-video')
}
