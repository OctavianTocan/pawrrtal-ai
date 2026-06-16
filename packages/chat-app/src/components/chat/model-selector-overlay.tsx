/**
 * `ModelSelectorOverlay` — the reasoning-tier popover that rises from the
 * composer when the model pill is tapped. Lists each tier with its icon,
 * name, and subtitle, and a checkmark on the active tier.
 */
import { StyleSheet, View } from 'react-native';
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

  return (
    <View style={StyleSheet.absoluteFill}>
      <OverlayBackdrop onDismiss={() => run(actions.setOverlay('none'))} />
      <Animated.View
        entering={FadeInDown.duration(duration.base)}
        exiting={FadeOutDown.duration(duration.fast)}
        style={styles.popover}
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
              <AppIcon name={model.icon as never} size={24} />
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

const styles = StyleSheet.create({
  popover: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.xl,
    bottom: 120,
    left: spacing.lg,
    overflow: 'hidden',
    paddingVertical: spacing.xs,
    position: 'absolute',
    width: 320,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  rowActive: { backgroundColor: colors.surface },
  text: { flex: 1, gap: spacing.xxs },
});
