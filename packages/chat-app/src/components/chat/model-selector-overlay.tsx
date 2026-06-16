/**
 * `ModelSelectorOverlay` — the reasoning-tier popover that rises from the
 * composer when the model pill is tapped. Lists each tier with its icon,
 * name, and subtitle, and a checkmark on the active tier.
 */
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useAppState, useCatalog, useRun } from '@/runtime';
import { OverlayBackdrop } from './overlay-backdrop';

/** Tier-selection popover anchored above the composer. */
export function ModelSelectorOverlay(): React.JSX.Element {
  const { selectedTier } = useAppState();
  const catalog = useCatalog();
  const run = useRun();
  const { width: screenWidth } = useWindowDimensions();
  // Clamp to the screen so the popover never runs past the right edge on
  // narrow devices (e.g. 320dp), where a fixed 320 + left inset would clip.
  const popoverWidth = Math.min(POPOVER_MAX_WIDTH, screenWidth - spacing.lg * 2);

  return (
    <View style={StyleSheet.absoluteFill}>
      <OverlayBackdrop onDismiss={() => run(actions.setOverlay('none'))} />
      <Animated.View
        entering={FadeInDown.duration(duration.base)}
        exiting={FadeOutDown.duration(duration.fast)}
        style={[styles.popover, { width: popoverWidth }]}
      >
        {catalog.models.map((model) => {
          const active = model.id === selectedTier;
          return (
            <Pressable
              accessibilityLabel={model.name}
              key={model.id}
              onPress={() => run(actions.selectTier(model.id))}
              style={[styles.row, active && styles.rowActive]}
            >
              <AppIcon name={model.icon} size={24} />
              <View style={styles.text}>
                <ThemedText variant="bodyStrong">{model.name}</ThemedText>
                <ThemedText color="textSecondary" variant="caption">
                  {model.subtitle}
                </ThemedText>
              </View>
              {active ? <AppIcon name="check" size={22} /> : null}
            </Pressable>
          );
        })}
      </Animated.View>
    </View>
  );
}

/** Preferred popover width on roomy screens; clamped down on narrow ones. */
const POPOVER_MAX_WIDTH = 250;

const styles = StyleSheet.create({
  popover: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.xxl,
    bottom: 140,
    left: spacing.lg,
    overflow: 'hidden',
    paddingVertical: spacing.xs,
    position: 'absolute',
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
  },
  // Selected row reads as a subtle LIGHTER band, not a darker sunken one.
  rowActive: { backgroundColor: colors.rowSelected },
  text: { flex: 1, gap: spacing.xxs },
});
