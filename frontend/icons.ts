/**
 * Lucide icon mapping for ZugaLife.
 *
 * Maps emoji characters (stored in DB) to Lucide Vue components.
 * This lets us render SVG icons everywhere without changing the backend.
 */

import {
  Smile,
  Frown,
  Angry,
  ShieldAlert,
  Moon,
  Sparkles,
  Meh,
  Heart,
  Flame,
  Lightbulb,
  Leaf,
  Zap,
  Wind,
  ScanEye,
  HeartHandshake,
  Mountain,
  HandHeart,
  Snowflake,
  CloudRain,
  Waves,
  TreePine,
  Bell,
  VolumeX,
  Dumbbell,
  Droplets,
  BookOpen,
  Brain,
  Salad,
  MonitorOff,
  Footprints,
  CircleDot,
  type LucideIcon,
} from 'lucide-vue-next'

// --- Mood icons ---
export const moodIcons: Record<string, LucideIcon> = {
  '😊': Smile,
  '😢': Frown,
  '😠': Angry,
  '😰': ShieldAlert,
  '😴': Moon,
  '🤩': Sparkles,
  '😐': Meh,
  '🥰': Heart,
  '😤': Flame,
  '🤔': Lightbulb,
  '😌': Leaf,
  '💪': Zap,
}

// --- Meditation type icons ---
export const meditationTypeIcons: Record<string, LucideIcon> = {
  breathing: Wind,
  body_scan: ScanEye,
  loving_kindness: HeartHandshake,
  visualization: Mountain,
  gratitude: HandHeart,
  stress_relief: Snowflake,
}

// --- Ambience icons ---
export const ambienceIcons: Record<string, LucideIcon> = {
  rain: CloudRain,
  ocean: Waves,
  forest: TreePine,
  bowls: Bell,
  silence: VolumeX,
}

// --- Habit icons (emoji chars + Lucide icon names → Lucide components) ---
export const habitIcons: Record<string, LucideIcon> = {
  // Legacy emoji keys (preset habits stored as emoji in DB)
  '😴': Moon,
  '\uD83C\uDFCB': Dumbbell,
  '🏋': Dumbbell,
  '💧': Droplets,
  '🧘': Brain,
  '📖': BookOpen,
  '🥗': Salad,
  '📵': MonitorOff,
  '🙏': HandHeart,
  '🚶': Footprints,
  // Icon name keys (custom habits stored as icon names)
  'dumbbell': Dumbbell,
  'moon': Moon,
  'droplets': Droplets,
  'brain': Brain,
  'book-open': BookOpen,
  'salad': Salad,
  'heart': Heart,
  'leaf': Leaf,
  'zap': Zap,
  'footprints': Footprints,
  'smile': Smile,
  'flame': Flame,
  'sparkles': Sparkles,
  'wind': Wind,
  'mountain': Mountain,
  'waves': Waves,
  'monitor-off': MonitorOff,
  'hand-heart': HandHeart,
  'snowflake': Snowflake,
  'circle-dot': CircleDot,
}

// --- Icon picker options for custom habits ---
export interface IconOption {
  name: string
  icon: LucideIcon
  label: string
}

export const habitIconPicker: IconOption[] = [
  { name: 'dumbbell', icon: Dumbbell, label: 'Exercise' },
  { name: 'moon', icon: Moon, label: 'Sleep' },
  { name: 'droplets', icon: Droplets, label: 'Water' },
  { name: 'brain', icon: Brain, label: 'Mind' },
  { name: 'book-open', icon: BookOpen, label: 'Reading' },
  { name: 'salad', icon: Salad, label: 'Food' },
  { name: 'heart', icon: Heart, label: 'Love' },
  { name: 'leaf', icon: Leaf, label: 'Nature' },
  { name: 'zap', icon: Zap, label: 'Energy' },
  { name: 'footprints', icon: Footprints, label: 'Walking' },
  { name: 'smile', icon: Smile, label: 'Happy' },
  { name: 'flame', icon: Flame, label: 'Fire' },
  { name: 'sparkles', icon: Sparkles, label: 'Star' },
  { name: 'wind', icon: Wind, label: 'Breath' },
  { name: 'mountain', icon: Mountain, label: 'Mountain' },
  { name: 'waves', icon: Waves, label: 'Ocean' },
  { name: 'monitor-off', icon: MonitorOff, label: 'Screen Off' },
  { name: 'hand-heart', icon: HandHeart, label: 'Gratitude' },
  { name: 'snowflake', icon: Snowflake, label: 'Calm' },
  { name: 'circle-dot', icon: CircleDot, label: 'Focus' },
]

// --- Generic fallback: try habit map, then mood map, then null ---
export function getIcon(emoji: string): LucideIcon | null {
  return habitIcons[emoji] || moodIcons[emoji] || null
}

// Re-export Leaf for the ZugaLife brand icon
export { Leaf as BrandIcon }
