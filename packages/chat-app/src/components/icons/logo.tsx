/**
 * `Logo` — the app's brand mark: an original "empty set" geometric glyph
 * (a thin ring crossed by a single diagonal slash that overshoots the ring
 * slightly at each end). Lives in its own file so it can be reused as the
 * large home watermark and as a small brand glyph.
 */
import Svg, { Circle, Line } from 'react-native-svg';
import { colors } from '@/constants/colors';

/** Props for {@link Logo}. */
export interface LogoProps {
  /** Square size in px. */
  size?: number;
  /** Stroke color (defaults to the watermark token). */
  color?: string;
  /** Stroke weight in viewBox units (100×100 space). */
  strokeWidth?: number;
}

/** Render the brand glyph at a given size. */
export function Logo({
  size = 132,
  color = colors.watermark,
  strokeWidth = 4.5,
}: LogoProps): React.JSX.Element {
  return (
    <Svg fill="none" height={size} viewBox="0 0 100 100" width={size}>
      <Circle cx={50} cy={50} r={31} stroke={color} strokeWidth={strokeWidth} />
      <Line
        stroke={color}
        strokeLinecap="round"
        strokeWidth={strokeWidth}
        x1={26}
        x2={74}
        y1={74}
        y2={26}
      />
    </Svg>
  );
}
