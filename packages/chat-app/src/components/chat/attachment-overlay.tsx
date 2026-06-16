/**
 * `AttachmentOverlay` — the `+` menu that rises from the composer with the
 * attachment sources (Camera, Gallery, Files) and the tool rows (Skills,
 * Connectors), separated by a hairline divider.
 */
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInDown, FadeOutDown } from 'react-native-reanimated';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon, type IconName } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { duration } from '@/constants/motion';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useRun } from '@/runtime';
import { OverlayBackdrop } from './overlay-backdrop';

/** One attachment-menu entry. */
interface AttachmentItem {
  readonly id: string;
  readonly label: string;
  readonly icon: IconName;
}

/** Media-source group (above the divider). */
const SOURCES: readonly AttachmentItem[] = [
  { id: 'camera', label: 'Camera', icon: 'camera' },
  { id: 'gallery', label: 'Gallery', icon: 'gallery' },
  { id: 'files', label: 'Files', icon: 'files' },
];

/** Tool group (below the divider). */
const TOOLS: readonly AttachmentItem[] = [
  { id: 'skills', label: 'Skills', icon: 'skills' },
  { id: 'connectors', label: 'Connectors', icon: 'connectors' },
];

/** Attachment / tools popover anchored above the composer. */
export function AttachmentOverlay(): React.JSX.Element {
  const run = useRun();
  const dismiss = (): void => run(actions.setOverlay('none'));

  return (
    <View style={StyleSheet.absoluteFill}>
      <OverlayBackdrop onDismiss={dismiss} />
      <Animated.View
        entering={FadeInDown.duration(duration.base)}
        exiting={FadeOutDown.duration(duration.fast)}
        style={styles.popover}
      >
        {SOURCES.map((item) => (
          <AttachmentRow icon={item.icon} key={item.id} label={item.label} onPress={dismiss} />
        ))}
        <View style={styles.divider} />
        {TOOLS.map((item) => (
          <AttachmentRow icon={item.icon} key={item.id} label={item.label} onPress={dismiss} />
        ))}
      </Animated.View>
    </View>
  );
}

/** A single tappable attachment row. */
function AttachmentRow({
  icon,
  label,
  onPress,
}: {
  readonly icon: IconName;
  readonly label: string;
  readonly onPress: () => void;
}): React.JSX.Element {
  return (
    <Pressable accessibilityLabel={label} onPress={onPress} style={styles.row}>
      <AppIcon name={icon} size={22} />
      <ThemedText variant="bodyStrong">{label}</ThemedText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  popover: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.xl,
    bottom: 120,
    left: spacing.lg,
    overflow: 'hidden',
    paddingVertical: spacing.sm,
    position: 'absolute',
    width: 260,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  divider: {
    backgroundColor: colors.border,
    height: StyleSheet.hairlineWidth,
    marginHorizontal: spacing.lg,
    marginVertical: spacing.xs,
  },
});
