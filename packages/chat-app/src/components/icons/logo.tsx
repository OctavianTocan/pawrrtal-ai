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
  strokeWidth = 4,
}: LogoProps): React.JSX.Element {
  return (
    <Svg fill="none" height={size} viewBox="0 0 100 100" width={size}>
      <Circle cx={50} cy={50} r={31} stroke={color} strokeWidth={strokeWidth} />
      {/* Slash overshoots the ring well past both ends into sharp points
          (the "empty set" ∅ form) — the reference extends noticeably beyond
          the ring at top-right and bottom-left. */}
      <Line
        stroke={color}
        strokeLinecap="round"
        strokeWidth={strokeWidth}
        x1={14}
        x2={86}
        y1={90}
        y2={10}
      />
    </Svg>
  );
}
