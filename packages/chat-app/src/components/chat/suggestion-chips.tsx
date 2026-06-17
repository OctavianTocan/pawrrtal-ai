/**
 * `SuggestionChips` — the horizontally-scrolling row of quick-action chips
 * shown just above the composer on the empty home canvas.
 */
import { ScrollView, StyleSheet } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon, type IconName } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';

/** A single suggestion chip definition. */
interface Suggestion {
  readonly id: string;
  readonly label: string;
  readonly icon: IconName;
}

/** Chips shown on the home canvas, in order. */
const SUGGESTIONS: readonly Suggestion[] = [
  { id: 'videos', label: 'Create Videos', icon: 'create-videos' },
  { id: 'edit', label: 'Edit image', icon: 'edit-image' },
  { id: 'voice', label: 'Voice', icon: 'waveform' },
];

/** Row of quick-action suggestion chips. */
export function SuggestionChips(): React.JSX.Element {
  return (
    <ScrollView
      contentContainerStyle={styles.content}
      horizontal
      showsHorizontalScrollIndicator={false}
      style={styles.scroll}
    >
      {SUGGESTIONS.map((suggestion) => (
        <Pressable accessibilityLabel={suggestion.label} key={suggestion.id} style={styles.chip}>
          <AppIcon name={suggestion.icon} size={18} />
          <ThemedText style={styles.label} variant="label">
            {suggestion.label}
          </ThemedText>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flexGrow: 0 },
  content: { gap: spacing.md, paddingHorizontal: spacing.md },
  chip: {
    alignItems: 'center',
    backgroundColor: colors.surfaceMuted,
    borderRadius: radii.md,
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
  },
  label: { marginRight: spacing.xxs },
});
