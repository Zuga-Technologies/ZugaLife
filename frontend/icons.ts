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
  // Extended icon set
  Activity,
  Bike,
  BicepsFlexed,
  Target,
  HeartPulse,
  Pill,
  Eye,
  MoonStar,
  BrainCog,
  Palette,
  Paintbrush,
  Pencil,
  Pen,
  Music,
  Headphones,
  Coffee,
  CookingPot,
  Cookie,
  Wine,
  Beer,
  Cat,
  Dog,
  Bird,
  Laptop,
  Code,
  Briefcase,
  MessageCircle,
  Phone,
  Mail,
  Users,
  Calendar,
  Clock,
  Timer,
  Bed,
  School,
  BookOpenCheck,
  Bookmark,
  TrendingUp,
  Trophy,
  Medal,
  Star,
  Sun,
  Sunrise,
  CloudSun,
  Umbrella,
  Shirt,
  Scissors,
  Camera,
  Film,
  Gamepad2,
  Puzzle,
  Map,
  Compass,
  Globe,
  Plane,
  Car,
  Ship,
  Trees,
  Flower2,
  Sprout,
  Apple,
  Banana,
  Cherry,
  Grape,
  Cigarette,
  CircleOff,
  ShieldCheck,
  Coins,
  PiggyBank,
  Wallet,
  GraduationCap,
  Languages,
  Mic,
  Piano,
  Guitar,
  Drum,
  Paintbrush2,
  Brush,
  Hammer,
  Wrench,
  Stethoscope,
  Syringe,
  Thermometer,
  Baby,
  HandMetal,
  PartyPopper,
  Gift,
  Rocket,
  Atom,
  Infinity,
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
// All icon names used in habitIconPicker must have an entry here for rendering.
const _iconNameMap: Record<string, LucideIcon> = {
  'dumbbell': Dumbbell, 'moon': Moon, 'droplets': Droplets, 'brain': Brain,
  'book-open': BookOpen, 'salad': Salad, 'heart': Heart, 'leaf': Leaf,
  'zap': Zap, 'footprints': Footprints, 'smile': Smile, 'flame': Flame,
  'sparkles': Sparkles, 'wind': Wind, 'mountain': Mountain, 'waves': Waves,
  'monitor-off': MonitorOff, 'hand-heart': HandHeart, 'snowflake': Snowflake,
  'circle-dot': CircleDot,
  // Extended
  'activity': Activity, 'bike': Bike, 'biceps-flexed': BicepsFlexed,
  'target': Target, 'heart-pulse': HeartPulse, 'pill': Pill, 'eye': Eye,
  'moon-star': MoonStar, 'brain-cog': BrainCog, 'palette': Palette,
  'paintbrush': Paintbrush, 'pencil': Pencil, 'pen': Pen, 'music': Music,
  'headphones': Headphones, 'coffee': Coffee, 'cooking-pot': CookingPot,
  'cookie': Cookie, 'wine': Wine, 'beer': Beer, 'cat': Cat, 'dog': Dog,
  'bird': Bird, 'laptop': Laptop, 'code': Code, 'briefcase': Briefcase,
  'message-circle': MessageCircle, 'phone': Phone, 'mail': Mail,
  'users': Users, 'calendar': Calendar, 'clock': Clock, 'timer': Timer,
  'bed': Bed, 'school': School, 'book-open-check': BookOpenCheck,
  'bookmark': Bookmark, 'trending-up': TrendingUp, 'trophy': Trophy,
  'medal': Medal, 'star': Star, 'sun': Sun, 'sunrise': Sunrise,
  'cloud-sun': CloudSun, 'umbrella': Umbrella, 'shirt': Shirt,
  'scissors': Scissors, 'camera': Camera, 'film': Film,
  'gamepad-2': Gamepad2, 'puzzle': Puzzle, 'map': Map, 'compass': Compass,
  'globe': Globe, 'plane': Plane, 'car': Car, 'ship': Ship,
  'trees': Trees, 'flower-2': Flower2, 'sprout': Sprout,
  'apple': Apple, 'banana': Banana, 'cherry': Cherry, 'grape': Grape,
  'cigarette': Cigarette, 'circle-off': CircleOff, 'shield-check': ShieldCheck,
  'coins': Coins, 'piggy-bank': PiggyBank, 'wallet': Wallet,
  'graduation-cap': GraduationCap, 'languages': Languages, 'mic': Mic,
  'piano': Piano, 'guitar': Guitar, 'drum': Drum,
  'paintbrush-2': Paintbrush2, 'brush': Brush, 'hammer': Hammer,
  'wrench': Wrench, 'stethoscope': Stethoscope, 'syringe': Syringe,
  'thermometer': Thermometer, 'baby': Baby, 'hand-metal': HandMetal,
  'party-popper': PartyPopper, 'gift': Gift, 'rocket': Rocket,
  'atom': Atom, 'infinity': Infinity, 'lightbulb': Lightbulb,
  'tree-pine': TreePine, 'cloud-rain': CloudRain, 'bell': Bell,
  'heart-handshake': HeartHandshake,
}

export const habitIcons: Record<string, LucideIcon> = {
  // Legacy emoji keys (preset habits stored as emoji in DB)
  '😴': Moon, '\uD83C\uDFCB': Dumbbell, '🏋': Dumbbell, '💧': Droplets,
  '🧘': Brain, '📖': BookOpen, '🥗': Salad, '📵': MonitorOff,
  '🙏': HandHeart, '🚶': Footprints,
  // All icon name keys
  ..._iconNameMap,
}

// --- Icon picker options for custom habits ---
export interface IconOption {
  name: string
  icon: LucideIcon
  label: string
}

export interface IconCategory {
  label: string
  icons: IconOption[]
}

// Top row: most common habit icons (shown by default)
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

// Expanded categories (shown when "more" is clicked)
export const habitIconCategories: IconCategory[] = [
  {
    label: 'Fitness',
    icons: [
      { name: 'activity', icon: Activity, label: 'Activity' },
      { name: 'bike', icon: Bike, label: 'Cycling' },
      { name: 'biceps-flexed', icon: BicepsFlexed, label: 'Strength' },
      { name: 'target', icon: Target, label: 'Target' },
      { name: 'trophy', icon: Trophy, label: 'Trophy' },
      { name: 'medal', icon: Medal, label: 'Medal' },
      { name: 'trending-up', icon: TrendingUp, label: 'Progress' },
    ],
  },
  {
    label: 'Health',
    icons: [
      { name: 'heart-pulse', icon: HeartPulse, label: 'Heart Rate' },
      { name: 'pill', icon: Pill, label: 'Medication' },
      { name: 'stethoscope', icon: Stethoscope, label: 'Doctor' },
      { name: 'thermometer', icon: Thermometer, label: 'Temperature' },
      { name: 'syringe', icon: Syringe, label: 'Vaccine' },
      { name: 'eye', icon: Eye, label: 'Vision' },
      { name: 'apple', icon: Apple, label: 'Apple' },
      { name: 'cherry', icon: Cherry, label: 'Fruit' },
      { name: 'banana', icon: Banana, label: 'Banana' },
      { name: 'grape', icon: Grape, label: 'Grapes' },
    ],
  },
  {
    label: 'Wellness',
    icons: [
      { name: 'bed', icon: Bed, label: 'Rest' },
      { name: 'moon-star', icon: MoonStar, label: 'Night' },
      { name: 'sun', icon: Sun, label: 'Morning' },
      { name: 'sunrise', icon: Sunrise, label: 'Sunrise' },
      { name: 'shield-check', icon: ShieldCheck, label: 'Protection' },
      { name: 'cigarette', icon: Cigarette, label: 'Smoking' },
      { name: 'circle-off', icon: CircleOff, label: 'Quit' },
      { name: 'baby', icon: Baby, label: 'Parenting' },
    ],
  },
  {
    label: 'Mind & Learning',
    icons: [
      { name: 'brain-cog', icon: BrainCog, label: 'Think' },
      { name: 'lightbulb', icon: Lightbulb, label: 'Ideas' },
      { name: 'school', icon: School, label: 'Study' },
      { name: 'graduation-cap', icon: GraduationCap, label: 'Graduate' },
      { name: 'book-open-check', icon: BookOpenCheck, label: 'Study Done' },
      { name: 'bookmark', icon: Bookmark, label: 'Bookmark' },
      { name: 'languages', icon: Languages, label: 'Language' },
      { name: 'puzzle', icon: Puzzle, label: 'Puzzle' },
      { name: 'atom', icon: Atom, label: 'Science' },
    ],
  },
  {
    label: 'Creative',
    icons: [
      { name: 'palette', icon: Palette, label: 'Art' },
      { name: 'paintbrush', icon: Paintbrush, label: 'Paint' },
      { name: 'paintbrush-2', icon: Paintbrush2, label: 'Brush' },
      { name: 'pencil', icon: Pencil, label: 'Write' },
      { name: 'pen', icon: Pen, label: 'Pen' },
      { name: 'camera', icon: Camera, label: 'Photo' },
      { name: 'film', icon: Film, label: 'Video' },
      { name: 'scissors', icon: Scissors, label: 'Craft' },
    ],
  },
  {
    label: 'Music',
    icons: [
      { name: 'music', icon: Music, label: 'Music' },
      { name: 'headphones', icon: Headphones, label: 'Listen' },
      { name: 'mic', icon: Mic, label: 'Sing' },
      { name: 'piano', icon: Piano, label: 'Piano' },
      { name: 'guitar', icon: Guitar, label: 'Guitar' },
      { name: 'drum', icon: Drum, label: 'Drums' },
    ],
  },
  {
    label: 'Food & Drink',
    icons: [
      { name: 'coffee', icon: Coffee, label: 'Coffee' },
      { name: 'cooking-pot', icon: CookingPot, label: 'Cooking' },
      { name: 'cookie', icon: Cookie, label: 'Baking' },
      { name: 'wine', icon: Wine, label: 'Wine' },
      { name: 'beer', icon: Beer, label: 'Beer' },
    ],
  },
  {
    label: 'Social',
    icons: [
      { name: 'users', icon: Users, label: 'Friends' },
      { name: 'message-circle', icon: MessageCircle, label: 'Chat' },
      { name: 'phone', icon: Phone, label: 'Call' },
      { name: 'mail', icon: Mail, label: 'Email' },
      { name: 'heart-handshake', icon: HeartHandshake, label: 'Connect' },
      { name: 'gift', icon: Gift, label: 'Gift' },
      { name: 'party-popper', icon: PartyPopper, label: 'Celebrate' },
    ],
  },
  {
    label: 'Work',
    icons: [
      { name: 'laptop', icon: Laptop, label: 'Computer' },
      { name: 'code', icon: Code, label: 'Code' },
      { name: 'briefcase', icon: Briefcase, label: 'Work' },
      { name: 'hammer', icon: Hammer, label: 'Build' },
      { name: 'wrench', icon: Wrench, label: 'Fix' },
      { name: 'coins', icon: Coins, label: 'Earn' },
      { name: 'piggy-bank', icon: PiggyBank, label: 'Save' },
      { name: 'wallet', icon: Wallet, label: 'Budget' },
      { name: 'rocket', icon: Rocket, label: 'Launch' },
    ],
  },
  {
    label: 'Outdoors',
    icons: [
      { name: 'tree-pine', icon: TreePine, label: 'Forest' },
      { name: 'trees', icon: Trees, label: 'Trees' },
      { name: 'flower-2', icon: Flower2, label: 'Garden' },
      { name: 'sprout', icon: Sprout, label: 'Grow' },
      { name: 'cloud-sun', icon: CloudSun, label: 'Weather' },
      { name: 'cloud-rain', icon: CloudRain, label: 'Rain' },
      { name: 'umbrella', icon: Umbrella, label: 'Umbrella' },
      { name: 'compass', icon: Compass, label: 'Explore' },
      { name: 'map', icon: Map, label: 'Map' },
    ],
  },
  {
    label: 'Pets',
    icons: [
      { name: 'cat', icon: Cat, label: 'Cat' },
      { name: 'dog', icon: Dog, label: 'Dog' },
      { name: 'bird', icon: Bird, label: 'Bird' },
    ],
  },
  {
    label: 'Travel & Time',
    icons: [
      { name: 'plane', icon: Plane, label: 'Travel' },
      { name: 'car', icon: Car, label: 'Drive' },
      { name: 'ship', icon: Ship, label: 'Sail' },
      { name: 'globe', icon: Globe, label: 'World' },
      { name: 'calendar', icon: Calendar, label: 'Schedule' },
      { name: 'clock', icon: Clock, label: 'Time' },
      { name: 'timer', icon: Timer, label: 'Timer' },
      { name: 'infinity', icon: Infinity, label: 'Forever' },
    ],
  },
  {
    label: 'Misc',
    icons: [
      { name: 'star', icon: Star, label: 'Star' },
      { name: 'bell', icon: Bell, label: 'Reminder' },
      { name: 'shirt', icon: Shirt, label: 'Outfit' },
      { name: 'brush', icon: Brush, label: 'Clean' },
      { name: 'gamepad-2', icon: Gamepad2, label: 'Gaming' },
      { name: 'hand-metal', icon: HandMetal, label: 'Rock' },
    ],
  },
]

// --- Generic fallback: try habit map, then mood map, then null ---
export function getIcon(emoji: string): LucideIcon | null {
  return habitIcons[emoji] || moodIcons[emoji] || null
}

// Re-export Leaf for the ZugaLife brand icon
export { Leaf as BrandIcon }
