/**
 * `Waveform` — the voice-capture amplitude strip. In the reference this is a
 * row of small dots (not vertical bars): a long run of faint, uniform dots
 * with a brighter, slightly larger cluster near the right edge that reads as
 * the "live" amplitude head.
 */
import { StyleSheet, View } from 'react-native';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';

/** Number of dots in the strip. */
const DOT_COUNT = 46;
/** How many trailing dots form the brighter "live" amplitude cluster. */
const LIVE_DOT_COUNT = 7;

/** True when the dot at `index` belongs to the trailing live cluster. */
function isLiveDot(index: number): boolean {
  return index >= DOT_COUNT - LIVE_DOT_COUNT;
}

/** Static dotted amplitude strip used inside the voice capture bar. */
export function Waveform(): React.JSX.Element {
  return (
    <View style={styles.row}>
      {Array.from({ length: DOT_COUNT }, (_, index) => (
        <View
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length static strip, index is the stable identity
          key={index}
          style={isLiveDot(index) ? styles.liveDot : styles.dot}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  // Stretch edge-to-edge across the pill; `space-between` spreads the dots
  // the full width with the bright cluster landing at the right edge.
  row: {
    alignItems: 'center',
    alignSelf: 'stretch',
    flexDirection: 'row',
    height: 12,
    justifyContent: 'space-between',
  },
  // Faint, uniform dots that make up the resting strip.
  dot: {
    backgroundColor: colors.textTertiary,
    borderRadius: radii.full,
    height: 2.5,
    width: 2.5,
  },
  // Brighter, slightly larger trailing cluster — the live amplitude head.
  liveDot: {
    backgroundColor: colors.textPrimary,
    borderRadius: radii.full,
    height: 3.5,
    width: 3.5,
  },
});
