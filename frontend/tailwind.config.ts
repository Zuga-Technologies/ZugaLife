import type { Config } from 'tailwindcss'
import preset from '../../ZugaCore/frontend/theme/tailwind.preset'

export default {
  presets: [preset],
  content: [
    './index.html',
    './*.{vue,ts}',
    '../../ZugaCore/frontend/**/*.{ts,css}',
  ],
  plugins: [],
} satisfies Config
