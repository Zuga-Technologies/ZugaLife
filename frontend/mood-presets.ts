/**
 * Mood definitions per theme preset.
 *
 * Each preset can override emoji and labels while keeping the same
 * underlying mood semantics (valence mapping stays consistent on the backend).
 *
 * The `key` field maps to the backend's canonical mood label for storage.
 * Only emoji and display label change per preset — the data model is stable.
 */

export interface MoodDefinition {
  /** Backend-canonical label (always English, used for API calls) */
  key: string
  /** Display emoji */
  emoji: string
  /** Display label shown to the user */
  label: string
}

const DEFAULT_MOODS: MoodDefinition[] = [
  { key: 'Happy', emoji: '😊', label: 'Happy' },
  { key: 'Sad', emoji: '😢', label: 'Sad' },
  { key: 'Angry', emoji: '😠', label: 'Angry' },
  { key: 'Anxious', emoji: '😰', label: 'Anxious' },
  { key: 'Tired', emoji: '😴', label: 'Tired' },
  { key: 'Excited', emoji: '🤩', label: 'Excited' },
  { key: 'Neutral', emoji: '😐', label: 'Neutral' },
  { key: 'Loved', emoji: '🥰', label: 'Loved' },
  { key: 'Frustrated', emoji: '😤', label: 'Frustrated' },
  { key: 'Thoughtful', emoji: '🤔', label: 'Thoughtful' },
  { key: 'Calm', emoji: '😌', label: 'Calm' },
  { key: 'Motivated', emoji: '💪', label: 'Motivated' },
]

const TAROT_MOODS: MoodDefinition[] = [
  { key: 'Happy', emoji: '☀️', label: 'The Sun' },
  { key: 'Sad', emoji: '🌊', label: 'The Moon' },
  { key: 'Angry', emoji: '⚡', label: 'The Tower' },
  { key: 'Anxious', emoji: '🌀', label: 'The Wheel' },
  { key: 'Tired', emoji: '🌙', label: 'The Hermit' },
  { key: 'Excited', emoji: '⭐', label: 'The Star' },
  { key: 'Neutral', emoji: '⚖️', label: 'Justice' },
  { key: 'Loved', emoji: '💫', label: 'The Lovers' },
  { key: 'Frustrated', emoji: '🔥', label: 'Strength' },
  { key: 'Thoughtful', emoji: '🔮', label: 'High Priestess' },
  { key: 'Calm', emoji: '🕊️', label: 'Temperance' },
  { key: 'Motivated', emoji: '🗡️', label: 'The Chariot' },
]

const BIBLICAL_MOODS: MoodDefinition[] = [
  { key: 'Happy', emoji: '✝️', label: 'Joyful' },
  { key: 'Sad', emoji: '🕊️', label: 'Sorrowful' },
  { key: 'Angry', emoji: '🔥', label: 'Righteous' },
  { key: 'Anxious', emoji: '🙏', label: 'Seeking' },
  { key: 'Tired', emoji: '🌿', label: 'Weary' },
  { key: 'Excited', emoji: '🌅', label: 'Exalted' },
  { key: 'Neutral', emoji: '📖', label: 'Contemplative' },
  { key: 'Loved', emoji: '❤️', label: 'Beloved' },
  { key: 'Frustrated', emoji: '⛰️', label: 'Tested' },
  { key: 'Thoughtful', emoji: '🕯️', label: 'Reflective' },
  { key: 'Calm', emoji: '☁️', label: 'Peaceful' },
  { key: 'Motivated', emoji: '🦁', label: 'Courageous' },
]

const MOOD_PRESETS: Record<string, MoodDefinition[]> = {
  default: DEFAULT_MOODS,
  tarot: TAROT_MOODS,
  biblical: BIBLICAL_MOODS,
}

/** Get mood definitions for the given theme preset ID */
export function getMoods(presetId: string): MoodDefinition[] {
  return MOOD_PRESETS[presetId] || DEFAULT_MOODS
}

/** Convert a display label back to the backend canonical key */
export function moodDisplayToKey(presetId: string, displayLabel: string): string {
  const moods = getMoods(presetId)
  const found = moods.find(m => m.label === displayLabel)
  return found ? found.key : displayLabel
}

/** Convert a backend key to the display label for the current preset */
export function moodKeyToDisplay(presetId: string, key: string): MoodDefinition | undefined {
  const moods = getMoods(presetId)
  return moods.find(m => m.key === key)
}
