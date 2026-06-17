/**
 * `Pressable` — the design-system pressable. Adds a light haptic on press
 * (native only) and a subtle opacity dim while held, so every interactive
 * surface in the app shares the same touch feedback.
 */
import * as Haptics from 'expo-haptics';
import { Platform, type PressableProps, Pressable as RNPressable } from 'react-native';

/** Props for {@link Pressable}. */
export type AppPressableProps = PressableProps & {
  /** Disable the press haptic (e.g. for high-frequency controls). */
  noHaptic?: boolean;
};

/** Pressable with shared haptic + pressed-opacity feedback. */
export function Pressable({
  noHaptic = false,
  onPress,
  style,
  children,
  ...rest
}: AppPressableProps): React.JSX.Element {
  // Only behave interactively when an action is supplied. Without this guard,
  // placeholder rows (settings entries, chips) would dim and fire haptics on
  // press while doing nothing, giving false interactive feedback.
  const interactive = typeof onPress === 'function';

  const handlePress: PressableProps['onPress'] = interactive
    ? (event) => {
        if (!noHaptic && Platform.OS !== 'web') {
          void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        }
        onPress?.(event);
      }
    : undefined;

  return (
    <RNPressable
      onPress={handlePress}
      style={(state) => [
        interactive && state.pressed ? { opacity: 0.6 } : null,
        typeof style === 'function' ? style(state) : style,
      ]}
      {...rest}
    >
      {children}
    </RNPressable>
  );
}
