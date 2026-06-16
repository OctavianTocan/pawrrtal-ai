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
  const handlePress: PressableProps['onPress'] = (event) => {
    if (!noHaptic && Platform.OS !== 'web') {
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    onPress?.(event);
  };

  return (
    <RNPressable
      onPress={handlePress}
      style={(state) => [
        { opacity: state.pressed ? 0.6 : 1 },
        typeof style === 'function' ? style(state) : style,
      ]}
      {...rest}
    >
      {children}
    </RNPressable>
  );
}
