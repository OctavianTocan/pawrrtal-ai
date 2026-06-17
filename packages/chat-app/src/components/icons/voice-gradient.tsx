/**
 * `VoiceCaptureGradient` — the subtle horizontal tint that fills the voice
 * capture pill behind the waveform. In the reference the pill is only barely
 * lifted off the black canvas with a faint indigo→teal sweep, NOT a bright
 * teal band. Rendered as an SVG so the stop colors stay token-driven without
 * pulling in `expo-linear-gradient` (`react-native-svg` is already a dep).
 */
import { StyleSheet } from 'react-native';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';
import { colors } from '@/constants/colors';

/** Full-bleed subtle gradient backdrop for the voice capture pill. */
export function VoiceCaptureGradient(): React.JSX.Element {
  return (
    <Svg height="100%" style={StyleSheet.absoluteFill} width="100%">
      <Defs>
        {/* Left→right sweep: faint indigo edge, neutral middle, faint teal edge. */}
        <LinearGradient id="voiceSweep" x1="0" x2="1" y1="0" y2="0">
          <Stop offset="0" stopColor={colors.voiceStart} />
          <Stop offset="0.5" stopColor={colors.voiceMid} />
          <Stop offset="1" stopColor={colors.voiceEnd} />
        </LinearGradient>
      </Defs>
      <Rect fill="url(#voiceSweep)" height="100%" width="100%" />
    </Svg>
  );
}
