/**
 * `VoiceOverlay` — the full-screen voice-capture surface. Shows the capture
 * hints ("Swipe up to send", "Swipe left to cancel"), an animated waveform
 * strip, and the cancel (✕) / confirm (✓) controls.
 */

import { BlurView } from 'expo-blur';
import { StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { FadeIn, FadeInUp, FadeOut, runOnJS } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { VoiceCaptureGradient } from '@/components/icons/voice-gradient';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useRun } from '@/runtime';
import { Waveform } from './waveform';

/** Drag distance (px) past which a swipe dismisses the capture surface. */
const SWIPE_DISMISS_PX = 60;

/** Full-screen voice capture overlay. */
export function VoiceOverlay(): React.JSX.Element {
  const run = useRun();
  const insets = useSafeAreaInsets();
  const dismiss = (): void => run(actions.setOverlay('none'));

  // Honor the on-screen hints: swiping up (send) or left (cancel) both close
  // the capture surface — there's no model wired yet, so both just dismiss.
  const swipe = Gesture.Pan().onEnd((event) => {
    'worklet';
    if (event.translationY < -SWIPE_DISMISS_PX || event.translationX < -SWIPE_DISMISS_PX) {
      runOnJS(dismiss)();
    }
  });

  return (
    <Animated.View
      entering={FadeIn.duration(duration.base)}
      exiting={FadeOut.duration(duration.fast)}
      style={[StyleSheet.absoluteFill, styles.container]}
    >
      {/* Light scrim — the home stays visible behind the capture bar, matching
          the reference (not an opaque black takeover). */}
      <BlurView intensity={20} style={StyleSheet.absoluteFill} tint="dark" />
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.scrim]} />
      <GestureDetector gesture={swipe}>
        <View style={styles.gestureArea}>
          <View style={styles.hintArea}>
            <AppIcon color="textSecondary" name="chevron-up" size={20} />
            <ThemedText color="textSecondary" variant="caption">
              Swipe up to send
            </ThemedText>
          </View>

          <Animated.View
            entering={FadeInUp.duration(duration.base)}
            style={[styles.captureBar, { marginBottom: insets.bottom + spacing.lg }]}
          >
            <Pressable accessibilityLabel="Cancel" onPress={dismiss} style={styles.cancelButton}>
              <AppIcon color="textPrimary" name="close" size={22} />
            </Pressable>

            <View style={styles.waveArea}>
              {/* Subtle dark tint fills the pill behind the dotted strip. */}
              <VoiceCaptureGradient />
              <View style={styles.waveContent}>
                <Waveform />
                <View style={styles.cancelHintRow}>
                  <AppIcon color="textSecondary" name="chevron-back" size={14} />
                  <ThemedText color="textSecondary" variant="caption">
                    Swipe left to cancel
                  </ThemedText>
                </View>
              </View>
            </View>

            <Pressable accessibilityLabel="Confirm" onPress={dismiss} style={styles.confirmButton}>
              <AppIcon color="onAccent" name="check" size={22} />
            </Pressable>
          </Animated.View>
        </View>
      </GestureDetector>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.transparent,
  },
  scrim: { backgroundColor: colors.background, opacity: 0.2 },
  gestureArea: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  hintArea: {
    alignItems: 'center',
    flexDirection: 'row',
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
    backgroundColor: colors.surfaceMuted,
    borderRadius: radii.full,
    flex: 1,
    height: 56,
    overflow: 'hidden',
  },
  // Full-width dotted strip toward the top, the cancel hint centered below.
  waveContent: {
    flex: 1,
    justifyContent: 'space-evenly',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  cancelHintRow: {
    alignItems: 'center',
    alignSelf: 'center',
    flexDirection: 'row',
    gap: spacing.xxs,
  },
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
