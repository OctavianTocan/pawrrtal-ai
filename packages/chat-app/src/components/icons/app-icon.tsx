/**
 * `AppIcon` — the single icon registry for the app. Components reference a
 * semantic name; this file maps it to a concrete Hugeicons glyph rendered at a
 * 1px stroke (per the brand spec), so swapping a glyph never touches a feature
 * file (per the icons-in-their-own-file rule).
 *
 * WHY deep per-icon imports (not the `@hugeicons/core-free-icons` barrel): the
 * barrel re-exports ~11k icon modules, which makes Metro crawl the whole set
 * and blows the open-file limit during a web export. Deep imports pull only
 * the ~45 glyphs actually used. Types for the `/*` subpath come from the
 * ambient declaration in `src/types/hugeicons.d.ts`.
 */
import Add01Icon from '@hugeicons/core-free-icons/Add01Icon';
import Alert02Icon from '@hugeicons/core-free-icons/Alert02Icon';
import ArrowDown01Icon from '@hugeicons/core-free-icons/ArrowDown01Icon';
import ArrowLeft01Icon from '@hugeicons/core-free-icons/ArrowLeft01Icon';
import ArrowRight01Icon from '@hugeicons/core-free-icons/ArrowRight01Icon';
import ArrowRightDoubleIcon from '@hugeicons/core-free-icons/ArrowRightDoubleIcon';
import ArrowUp01Icon from '@hugeicons/core-free-icons/ArrowUp01Icon';
import AudioWave02Icon from '@hugeicons/core-free-icons/AudioWave02Icon';
import BookOpen01Icon from '@hugeicons/core-free-icons/BookOpen01Icon';
import Camera01Icon from '@hugeicons/core-free-icons/Camera01Icon';
import Cancel01Icon from '@hugeicons/core-free-icons/Cancel01Icon';
import CheckmarkCircle01Icon from '@hugeicons/core-free-icons/CheckmarkCircle01Icon';
import ContrastIcon from '@hugeicons/core-free-icons/ContrastIcon';
import CrownIcon from '@hugeicons/core-free-icons/CrownIcon';
import DashboardSquare01Icon from '@hugeicons/core-free-icons/DashboardSquare01Icon';
import Database01Icon from '@hugeicons/core-free-icons/Database01Icon';
import DocumentValidationIcon from '@hugeicons/core-free-icons/DocumentValidationIcon';
import EnergyIcon from '@hugeicons/core-free-icons/EnergyIcon';
import File01Icon from '@hugeicons/core-free-icons/File01Icon';
import Film01Icon from '@hugeicons/core-free-icons/Film01Icon';
import FlashIcon from '@hugeicons/core-free-icons/FlashIcon';
import GridViewIcon from '@hugeicons/core-free-icons/GridViewIcon';
import Image01Icon from '@hugeicons/core-free-icons/Image01Icon';
import Image02Icon from '@hugeicons/core-free-icons/Image02Icon';
import IncognitoIcon from '@hugeicons/core-free-icons/IncognitoIcon';
import KidIcon from '@hugeicons/core-free-icons/KidIcon';
import LicenseIcon from '@hugeicons/core-free-icons/LicenseIcon';
import LifebuoyIcon from '@hugeicons/core-free-icons/LifebuoyIcon';
import Link01Icon from '@hugeicons/core-free-icons/Link01Icon';
import Logout01Icon from '@hugeicons/core-free-icons/Logout01Icon';
import Menu01Icon from '@hugeicons/core-free-icons/Menu01Icon';
import Mic01Icon from '@hugeicons/core-free-icons/Mic01Icon';
import MoreVerticalIcon from '@hugeicons/core-free-icons/MoreVerticalIcon';
import PencilEdit01Icon from '@hugeicons/core-free-icons/PencilEdit01Icon';
import PlugSocketIcon from '@hugeicons/core-free-icons/PlugSocketIcon';
import Pulse01Icon from '@hugeicons/core-free-icons/Pulse01Icon';
import Rocket01Icon from '@hugeicons/core-free-icons/Rocket01Icon';
import Search01Icon from '@hugeicons/core-free-icons/Search01Icon';
import Sent02Icon from '@hugeicons/core-free-icons/Sent02Icon';
import Settings01Icon from '@hugeicons/core-free-icons/Settings01Icon';
import Settings02Icon from '@hugeicons/core-free-icons/Settings02Icon';
import Shapes01Icon from '@hugeicons/core-free-icons/Shapes01Icon';
import SlidersHorizontalIcon from '@hugeicons/core-free-icons/SlidersHorizontalIcon';
import SquareLock01Icon from '@hugeicons/core-free-icons/SquareLock01Icon';
import Tick02Icon from '@hugeicons/core-free-icons/Tick02Icon';
import VoiceIcon from '@hugeicons/core-free-icons/VoiceIcon';
import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react-native';
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

/** Semantic name → concrete Hugeicons glyph. */
const REGISTRY: Record<IconName, IconSvgElement> = {
  menu: Menu01Icon,
  incognito: IncognitoIcon,
  mic: Mic01Icon,
  plus: Add01Icon,
  close: Cancel01Icon,
  check: Tick02Icon,
  'chevron-down': ArrowDown01Icon,
  'chevron-up': ArrowUp01Icon,
  'chevron-right': ArrowRight01Icon,
  'chevron-back': ArrowLeft01Icon,
  'chevrons-right': ArrowRightDoubleIcon,
  search: Search01Icon,
  settings: Settings01Icon,
  compose: PencilEdit01Icon,
  more: MoreVerticalIcon,
  camera: Camera01Icon,
  gallery: Image01Icon,
  files: File01Icon,
  skills: Shapes01Icon,
  connectors: PlugSocketIcon,
  heavy: GridViewIcon,
  expert: EnergyIcon,
  fast: FlashIcon,
  auto: Rocket01Icon,
  'create-videos': Film01Icon,
  'edit-image': Image02Icon,
  waveform: AudioWave02Icon,
  send: Sent02Icon,
  tasks: CheckmarkCircle01Icon,
  appearance: ContrastIcon,
  haptics: Pulse01Icon,
  widget: DashboardSquare01Icon,
  advanced: Settings02Icon,
  customize: SlidersHorizontalIcon,
  memory: BookOpen01Icon,
  voice: VoiceIcon,
  shared: Link01Icon,
  data: Database01Icon,
  licenses: LicenseIcon,
  terms: DocumentValidationIcon,
  privacy: SquareLock01Icon,
  report: LifebuoyIcon,
  kids: KidIcon,
  // The reference shows an "18" age-rating badge; the free icon set has no
  // numeric-18 glyph, so an alert reads as the closest "restricted content"
  // proxy without inlining a custom SVG.
  nsfw: Alert02Icon,
  signout: Logout01Icon,
  subscription: CrownIcon,
};

/** Stroke width for every glyph — 1px hairline per the brand spec. */
const STROKE_WIDTH = 1;

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
  return (
    <HugeiconsIcon
      color={colors[color]}
      icon={REGISTRY[name]}
      size={size}
      strokeWidth={STROKE_WIDTH}
    />
  );
}
