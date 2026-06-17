/**
 * `ModelSelectorOverlay` — the reasoning-tier popover that rises from the
 * composer when the model pill is tapped. Lists each tier with its icon,
 * name, and subtitle, and a checkmark on the active tier.
 */
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { Easing, FadeOut, ZoomIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
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
  const insets = useSafeAreaInsets();
  // Clamp to the screen so the popover never runs past the right edge on
  // narrow devices (e.g. 320dp), where a fixed 320 + left inset would clip.
  const popoverWidth = Math.min(POPOVER_MAX_WIDTH, screenWidth - spacing.lg * 2);

  return (
    <View style={StyleSheet.absoluteFill}>
      <OverlayBackdrop onDismiss={() => run(actions.setOverlay('none'))} variant="plain" />
      {/* Scale up from the model pill (bottom-left of the composer), ~375ms
          ease-out — matching the reference. `transformOrigin` anchors the
          scale to the trigger corner rather than the popover center. */}
      <Animated.View
        entering={ZoomIn.duration(duration.modelPopover).easing(Easing.out(Easing.cubic))}
        exiting={FadeOut.duration(duration.fast)}
        style={[styles.popover, { bottom: POPOVER_BOTTOM + insets.bottom, width: popoverWidth }]}
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
const POPOVER_MAX_WIDTH = 192;
/** Base gap above the composer; the bottom safe-area inset is added on top. */
const POPOVER_BOTTOM = 96;

const styles = StyleSheet.create({
  popover: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.xxl,
    left: spacing.lg,
    overflow: 'hidden',
    paddingVertical: spacing.sm,
    position: 'absolute',
    // Grow from the trigger (model pill) corner, not the popover center.
    transformOrigin: 'bottom left',
  },
  // Taller rows: the reference tiers span ~35% more height than a compact
  // list, so each row gets generous vertical padding.
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
  },
  // Selected row reads as a subtle LIGHTER band, not a darker sunken one.
  rowActive: { backgroundColor: colors.rowSelected },
  text: { flex: 1, gap: spacing.xxs },
});
