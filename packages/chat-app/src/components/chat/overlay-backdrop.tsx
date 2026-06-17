/**
 * `OverlayBackdrop` — the dismiss layer behind popovers and sheets. Two
 * variants:
 * - `plain` (default for trigger-anchored popovers like the model selector and
 *   attachment menu): a fully transparent tap-to-dismiss layer. The reference
 *   recording shows these popovers rising over the untouched home screen with
 *   NO dimming or blur, so the backdrop must be invisible.
 * - `scrim` (full-screen surfaces like voice capture): a background blur plus a
 *   subtle dark tint (a glass-like scrim) that fades in.
 * Tapping anywhere on the backdrop dismisses the overlay.
 */
import { BlurView } from 'expo-blur';
import { Pressable, StyleSheet } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';

/** Visual treatment of the dismiss layer. */
export type OverlayBackdropVariant = 'plain' | 'scrim';

/** Props for {@link OverlayBackdrop}. */
export interface OverlayBackdropProps {
  /** Called when the backdrop is tapped. */
  onDismiss: () => void;
  /**
   * `plain` (transparent, no blur/tint) for trigger-anchored popovers;
   * `scrim` (blur + dark tint) for full-screen surfaces. Defaults to `scrim`.
   */
  variant?: OverlayBackdropVariant;
}

/** Dismiss layer; transparent for popovers, blurred+tinted for full-screen surfaces. */
export function OverlayBackdrop({
  onDismiss,
  variant = 'scrim',
}: OverlayBackdropProps): React.JSX.Element {
  // Popovers in the reference rise over the plain screen — no dimming at all,
  // so the layer is just an invisible tap target with no entrance animation.
  if (variant === 'plain') {
    return (
      <Pressable accessibilityLabel="Dismiss" onPress={onDismiss} style={StyleSheet.absoluteFill} />
    );
  }

  return (
    <Animated.View
      entering={FadeIn.duration(duration.fast)}
      exiting={FadeOut.duration(duration.fast)}
      style={StyleSheet.absoluteFill}
    >
      <BlurView intensity={16} style={StyleSheet.absoluteFill} tint="dark" />
      <Pressable
        accessibilityLabel="Dismiss"
        onPress={onDismiss}
        style={[StyleSheet.absoluteFill, styles.tint]}
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  tint: { backgroundColor: colors.background, opacity: 0.28 },
});
