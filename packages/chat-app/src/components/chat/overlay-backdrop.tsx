/**
 * `OverlayBackdrop` — the dismiss layer behind popovers and sheets. Combines a
 * background blur with a subtle dark tint (a glass-like scrim) rather than a
 * flat opacity wash, and fades in. Tapping it dismisses the overlay.
 */
import { BlurView } from 'expo-blur';
import { Pressable, StyleSheet } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';

/** Props for {@link OverlayBackdrop}. */
export interface OverlayBackdropProps {
  /** Called when the backdrop is tapped. */
  onDismiss: () => void;
}

/** Blurred, dark-tinted, fade-in dismiss layer. */
export function OverlayBackdrop({ onDismiss }: OverlayBackdropProps): React.JSX.Element {
  return (
    <Animated.View
      entering={FadeIn.duration(duration.fast)}
      exiting={FadeOut.duration(duration.fast)}
      style={StyleSheet.absoluteFill}
    >
      <BlurView intensity={18} style={StyleSheet.absoluteFill} tint="dark" />
      <Pressable
        accessibilityLabel="Dismiss"
        onPress={onDismiss}
        style={[StyleSheet.absoluteFill, styles.tint]}
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  tint: { backgroundColor: colors.background, opacity: 0.45 },
});
