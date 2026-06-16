/**
 * `Waveform` — the voice-capture amplitude strip: a row of vertical bars whose
 * heights form a symmetric envelope, evoking a live recording meter.
 */
import { StyleSheet, View } from 'react-native';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';

/** Number of bars in the strip. */
const BAR_COUNT = 34;

/** Deterministic bar height (px) for a given index — a smooth-ish envelope. */
function barHeight(index: number): number {
  const phase = Math.sin(index * 0.9) + Math.sin(index * 0.35);
  return 6 + Math.abs(phase) * 12;
}

/** Static amplitude strip used inside the voice capture bar. */
export function Waveform(): React.JSX.Element {
  return (
    <View style={styles.row}>
      {Array.from({ length: BAR_COUNT }, (_, index) => (
        <View
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length static strip, index is the stable identity
          key={index}
          style={[styles.bar, { height: barHeight(index) }]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 3,
    height: 28,
    justifyContent: 'center',
  },
  bar: {
    backgroundColor: colors.voiceEnd,
    borderRadius: radii.full,
    width: 3,
  },
});
