/**
 * `VoiceOverlay` — the full-screen voice-capture surface. Shows the capture
 * hints ("Swipe up to send", "Swipe left to cancel"), an animated waveform
 * strip, and the cancel (✕) / confirm (✓) controls.
 */
import { StyleSheet, View } from 'react-native';
import Animated, { FadeIn, FadeInUp, FadeOut } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useRun } from '@/runtime';
import { Waveform } from './waveform';

/** Full-screen voice capture overlay. */
export function VoiceOverlay(): React.JSX.Element {
  const run = useRun();
  const insets = useSafeAreaInsets();
  const dismiss = (): void => run(actions.setOverlay('none'));

  return (
    <Animated.View
      entering={FadeIn.duration(duration.base)}
      exiting={FadeOut.duration(duration.fast)}
      style={[StyleSheet.absoluteFill, styles.container]}
    >
      <View style={styles.hintArea}>
        <AppIcon color="textSecondary" name="chevron-down" size={20} />
        <ThemedText color="textSecondary" variant="caption">
          Swipe up to send
        </ThemedText>
      </View>

      <Animated.View
        entering={FadeInUp.duration(duration.base)}
        style={[styles.captureBar, { marginBottom: insets.bottom + spacing.lg }]}
      >
        <Pressable accessibilityLabel="Cancel" onPress={dismiss} style={styles.cancelButton}>
          <AppIcon name="close" size={22} />
        </Pressable>

        <View style={styles.waveArea}>
          <Waveform />
          <ThemedText color="textSecondary" style={styles.cancelHint} variant="caption">
            Swipe left to cancel
          </ThemedText>
        </View>

        <Pressable accessibilityLabel="Confirm" onPress={dismiss} style={styles.confirmButton}>
          <AppIcon color="onAccent" name="check" size={22} />
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.background,
    justifyContent: 'flex-end',
  },
  hintArea: {
    alignItems: 'center',
    gap: spacing.xs,
    marginBottom: spacing.xxl,
  },
  captureBar: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    marginHorizontal: spacing.lg,
  },
  waveArea: {
    alignItems: 'center',
    backgroundColor: colors.voiceStart,
    borderRadius: radii.full,
    flex: 1,
    height: 56,
    justifyContent: 'center',
    overflow: 'hidden',
  },
  cancelHint: { position: 'absolute', bottom: spacing.xs },
  cancelButton: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 56,
    justifyContent: 'center',
    width: 56,
  },
  confirmButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: radii.full,
    height: 56,
    justifyContent: 'center',
    width: 56,
  },
});
