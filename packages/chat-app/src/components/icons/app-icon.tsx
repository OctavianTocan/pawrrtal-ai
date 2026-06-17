/**
 * `AppIcon` — the single icon registry for the app. Components reference a
 * semantic name; this file maps it to a concrete `@expo/vector-icons` glyph,
 * so swapping a glyph never touches a feature file (per the icons-in-their-
 * own-file rule).
 */
import { Feather, Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { type ColorToken, colors } from '@/constants/colors';

/** Every semantic icon name used across the app. */
export type IconName =
  | 'menu'
  | 'incognito'
  | 'mic'
  | 'plus'
  | 'close'
  | 'check'
  | 'chevron-down'
  | 'chevron-up'
  | 'chevron-right'
  | 'chevron-back'
  | 'chevrons-right'
  | 'search'
  | 'settings'
  | 'compose'
  | 'more'
  | 'camera'
  | 'gallery'
  | 'files'
  | 'skills'
  | 'connectors'
  | 'heavy'
  | 'expert'
  | 'fast'
  | 'auto'
  | 'create-videos'
  | 'edit-image'
  | 'waveform'
  | 'send'
  | 'tasks'
  | 'appearance'
  | 'haptics'
  | 'widget'
  | 'advanced'
  | 'customize'
  | 'memory'
  | 'voice'
  | 'shared'
  | 'data'
  | 'licenses'
  | 'terms'
  | 'privacy'
  | 'report'
  | 'kids'
  | 'nsfw'
  | 'signout'
  | 'subscription';

/** Supported vector-icon families. */
type IconFamily = 'ion' | 'mci' | 'feather';

/** Registry entry: which family + which glyph name. */
interface IconSpec {
  readonly family: IconFamily;
  readonly glyph: string;
}

/** Semantic name → concrete glyph. */
const REGISTRY: Record<IconName, IconSpec> = {
  menu: { family: 'feather', glyph: 'menu' },
  incognito: { family: 'mci', glyph: 'incognito' },
  mic: { family: 'feather', glyph: 'mic' },
  plus: { family: 'feather', glyph: 'plus' },
  close: { family: 'feather', glyph: 'x' },
  check: { family: 'feather', glyph: 'check' },
  'chevron-down': { family: 'feather', glyph: 'chevron-down' },
  'chevron-up': { family: 'feather', glyph: 'chevron-up' },
  'chevron-right': { family: 'feather', glyph: 'chevron-right' },
  'chevron-back': { family: 'feather', glyph: 'chevron-left' },
  'chevrons-right': { family: 'feather', glyph: 'chevrons-right' },
  search: { family: 'feather', glyph: 'search' },
  settings: { family: 'feather', glyph: 'settings' },
  compose: { family: 'feather', glyph: 'edit' },
  more: { family: 'feather', glyph: 'more-vertical' },
  camera: { family: 'feather', glyph: 'camera' },
  gallery: { family: 'feather', glyph: 'image' },
  files: { family: 'feather', glyph: 'file' },
  skills: { family: 'mci', glyph: 'shape-outline' },
  connectors: { family: 'mci', glyph: 'view-grid-plus-outline' },
  heavy: { family: 'mci', glyph: 'view-grid-outline' },
  expert: { family: 'feather', glyph: 'zap' },
  fast: { family: 'mci', glyph: 'lightning-bolt' },
  auto: { family: 'mci', glyph: 'rocket-launch-outline' },
  'create-videos': { family: 'feather', glyph: 'film' },
  'edit-image': { family: 'mci', glyph: 'image-edit-outline' },
  waveform: { family: 'mci', glyph: 'waveform' },
  send: { family: 'feather', glyph: 'arrow-up' },
  tasks: { family: 'feather', glyph: 'check-circle' },
  appearance: { family: 'mci', glyph: 'theme-light-dark' },
  haptics: { family: 'mci', glyph: 'vibrate' },
  widget: { family: 'mci', glyph: 'widgets-outline' },
  advanced: { family: 'mci', glyph: 'tune-variant' },
  customize: { family: 'feather', glyph: 'sliders' },
  memory: { family: 'feather', glyph: 'book-open' },
  voice: { family: 'mci', glyph: 'waveform' },
  shared: { family: 'feather', glyph: 'link-2' },
  data: { family: 'feather', glyph: 'database' },
  licenses: { family: 'feather', glyph: 'file-text' },
  terms: { family: 'mci', glyph: 'file-document-outline' },
  privacy: { family: 'feather', glyph: 'lock' },
  report: { family: 'feather', glyph: 'life-buoy' },
  kids: { family: 'mci', glyph: 'star-outline' },
  // The reference shows an "18" age-rating badge; this MDI build has no
  // numeric-18 glyph, so a shield-alert reads as the closest "restricted
  // content" proxy without inlining a custom SVG.
  nsfw: { family: 'mci', glyph: 'shield-alert-outline' },
  signout: { family: 'feather', glyph: 'log-out' },
  subscription: { family: 'mci', glyph: 'flash-outline' },
};

/** Props for {@link AppIcon}. */
export interface AppIconProps {
  /** Semantic icon name. */
  name: IconName;
  /** Glyph size in px. */
  size?: number;
  /** Color token (defaults to primary text). */
  color?: ColorToken;
}

/** Render a registry icon at a given size and token color. */
export function AppIcon({
  name,
  size = 24,
  color = 'textPrimary',
}: AppIconProps): React.JSX.Element {
  const spec = REGISTRY[name];
  const tint = colors[color];
  if (spec.family === 'ion') {
    return <Ionicons color={tint} name={spec.glyph as never} size={size} />;
  }
  if (spec.family === 'mci') {
    return <MaterialCommunityIcons color={tint} name={spec.glyph as never} size={size} />;
  }
  return <Feather color={tint} name={spec.glyph as never} size={size} />;
}
