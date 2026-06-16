/**
 * `MessageBubble` — one message in a conversation thread. User messages sit in
 * a right-aligned filled bubble; assistant messages render as left-aligned
 * full-width text (the common AI-chat treatment).
 */
import { StyleSheet, View } from 'react-native';
import { ThemedText } from '@/components/core/themed-text';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import type { Message } from '@/domain';

/** Props for {@link MessageBubble}. */
export interface MessageBubbleProps {
  /** The message to render. */
  message: Message;
}

/** A single chat message row. */
export function MessageBubble({ message }: MessageBubbleProps): React.JSX.Element {
  const isUser = message.role === 'user';
  return (
    <View style={[styles.row, isUser ? styles.rowUser : styles.rowAssistant]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.assistantBubble]}>
        <ThemedText color={isUser ? 'onAccent' : 'textPrimary'}>{message.text}</ThemedText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', marginBottom: spacing.lg },
  rowUser: { justifyContent: 'flex-end' },
  rowAssistant: { justifyContent: 'flex-start' },
  bubble: { borderRadius: radii.lg, maxWidth: '86%' },
  userBubble: {
    backgroundColor: colors.surfaceElevated,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  assistantBubble: { paddingVertical: spacing.xs },
});
