/**
 * `Logo` — the app's brand mark, an original geometric glyph (a ring crossed
 * by a tapered diagonal slash). Lives in its own file so it can be reused as
 * the large home watermark and as a small brand glyph without inlining SVG in
 * feature components.
 */
import Svg, { Circle, Path } from 'react-native-svg';
import { colors } from '@/constants/colors';

/** Props for {@link Logo}. */
export interface LogoProps {
  /** Square size in px. */
  size?: number;
  /** Stroke/fill color (defaults to the watermark token). */
  color?: string;
}

/** Render the brand glyph at a given size. */
export function Logo({ size = 160, color = colors.watermark }: LogoProps): React.JSX.Element {
  return (
    <Svg fill="none" height={size} viewBox="0 0 100 100" width={size}>
      <Circle cx={50} cy={50} r={34} stroke={color} strokeWidth={6} />
      <Path d="M30 70 L70 30" stroke={color} strokeLinecap="round" strokeWidth={8} />
      <Path d="M68 32 L78 22" stroke={color} strokeLinecap="round" strokeWidth={8} />
      <Path d="M32 68 L22 78" stroke={color} strokeLinecap="round" strokeWidth={8} />
    </Svg>
  );
}
