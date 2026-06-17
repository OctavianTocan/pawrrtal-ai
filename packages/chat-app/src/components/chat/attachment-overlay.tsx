/**
 * `AttachmentOverlay` — the `+` menu that rises from the composer with the
 * attachment sources (Camera, Gallery, Files) and the tool rows (Skills,
 * Connectors), separated by a hairline divider.
 */
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, { Easing, FadeOut, ZoomIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
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
  const { width: screenWidth } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  // Clamp so the menu never overflows the right edge on narrow devices.
  const menuWidth = Math.min(POPOVER_MAX_WIDTH, screenWidth - spacing.lg * 2);

  return (
    <View style={StyleSheet.absoluteFill}>
      <OverlayBackdrop onDismiss={dismiss} variant="plain" />
      {/* Scale up from the `+` button (bottom-left of the composer), ~250ms
          ease-out — matching the reference. */}
      <Animated.View
        entering={ZoomIn.duration(duration.attachmentPopover).easing(Easing.out(Easing.cubic))}
        exiting={FadeOut.duration(duration.fast)}
        style={[styles.popover, { bottom: POPOVER_BOTTOM + insets.bottom, width: menuWidth }]}
      >
        {SOURCES.map((item) => (
          <AttachmentRow icon={item.icon} key={item.id} label={item.label} onPress={dismiss} />
        ))}
        {/* Hairline separating the media sources from the tool rows, matching
            the reference's two-group layout. */}
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
      <AppIcon name={icon} size={24} />
      <ThemedText variant="title">{label}</ThemedText>
    </Pressable>
  );
}

/** Preferred menu width on roomy screens; clamped down on narrow ones. */
const POPOVER_MAX_WIDTH = 192;
/** Base gap above the composer; the bottom safe-area inset is added on top. */
const POPOVER_BOTTOM = 90;

const styles = StyleSheet.create({
  popover: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.xxl,
    left: spacing.lg,
    overflow: 'hidden',
    paddingVertical: spacing.sm,
    position: 'absolute',
    // Grow from the trigger (`+` button) corner, not the popover center.
    transformOrigin: 'bottom left',
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 2,
  },
  divider: {
    backgroundColor: colors.border,
    height: StyleSheet.hairlineWidth,
    marginHorizontal: spacing.lg,
    marginVertical: spacing.xs,
  },
});
