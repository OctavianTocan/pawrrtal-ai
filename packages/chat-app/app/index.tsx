/**
 * Home screen — the empty "Ask / Imagine" canvas with the centered brand
 * watermark, the suggestion chips, and the composer. The model, attachment,
 * and voice overlays are presented over this screen based on the store's
 * `overlay` state.
 */
import { KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Composer, HomeHeader, Overlays, SuggestionChips } from '@/components/chat';
import { Logo } from '@/components/icons/logo';
import { colors } from '@/constants/colors';
import { spacing } from '@/constants/spacing';

/** The home / landing screen. */
export default function HomeScreen(): React.JSX.Element {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      <View style={{ paddingTop: insets.top }}>
        <HomeHeader />
      </View>

      {/* Decorative only — must not intercept taps meant for the header/composer. */}
      <View pointerEvents="none" style={styles.watermark}>
        <Logo size={128} />
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.footer}
      >
        <SuggestionChips />
        <View style={[styles.composerWrap, { paddingBottom: insets.bottom + spacing.sm }]}>
          <Composer />
        </View>
      </KeyboardAvoidingView>

      <Overlays />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flex: 1 },
  watermark: {
    alignItems: 'center',
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  footer: { gap: spacing.md, marginTop: 'auto' },
  composerWrap: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
});
