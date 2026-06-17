/**
 * `ConversationRow` — one entry in the history drawer: the conversation title,
 * its relative time label, and an overflow (⋮) affordance.
 */
import { StyleSheet, View } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { spacing } from '@/constants/spacing';
import type { Conversation } from '@/domain';
import { actions, useRun } from '@/runtime';

/** Props for {@link ConversationRow}. */
export interface ConversationRowProps {
  /** The conversation to render. */
  conversation: Conversation;
}

/** A single conversation row in the history list; opens the thread on press. */
export function ConversationRow({ conversation }: ConversationRowProps): React.JSX.Element {
  const run = useRun();
  return (
    <View style={styles.row}>
      {/* Only the text region opens the thread; the ⋮ is a separate, visual-only
          affordance (no row-actions menu exists yet), so tapping it must not
          navigate. Keeping it outside the press target avoids that misroute. */}
      <Pressable
        accessibilityLabel={conversation.title}
        onPress={() => run(actions.openConversation(conversation.id))}
        style={styles.text}
      >
        <ThemedText numberOfLines={2} variant="bodyStrong">
          {conversation.title}
        </ThemedText>
        <ThemedText color="textSecondary" variant="caption">
          {conversation.timeLabel}
        </ThemedText>
      </Pressable>
      <View style={styles.more}>
        <AppIcon color="textSecondary" name="more" size={20} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  text: { flex: 1, gap: 1 },
  more: { paddingHorizontal: spacing.xs, paddingTop: spacing.xxs },
});
