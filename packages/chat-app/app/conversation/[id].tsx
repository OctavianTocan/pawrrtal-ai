/**
 * Conversation thread screen — a header (back + title), the scrollable message
 * list, and a composer bound to this conversation. Reads the reactive
 * conversations store, so messages appear as soon as they're sent.
 */

import { useLocalSearchParams } from 'expo-router';
import { useRef } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Composer, MessageBubble, Overlays } from '@/components/chat';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { spacing } from '@/constants/spacing';
import { actions, useConversations, useRun } from '@/runtime';

/** A single conversation's message thread. */
export default function ConversationScreen(): React.JSX.Element {
  const params = useLocalSearchParams<{ id: string }>();
  const id = typeof params.id === 'string' ? params.id : '';
  const conversations = useConversations();
  const run = useRun();
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);
  const conversation = conversations.find((item) => item.id === id);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable
          accessibilityLabel="Back"
          onPress={() => run(actions.navigateBack)}
          style={styles.iconButton}
        >
          <AppIcon name="chevron-back" size={24} />
        </Pressable>
        <ThemedText numberOfLines={1} style={styles.title} variant="bodyStrong">
          {conversation?.title ?? 'Conversation'}
        </ThemedText>
        <View style={styles.iconButton} />
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.body}
      >
        <ScrollView
          contentContainerStyle={styles.listContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          ref={scrollRef}
          showsVerticalScrollIndicator={false}
          style={styles.list}
        >
          {conversation?.messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </ScrollView>

        <View style={[styles.composerWrap, { paddingBottom: insets.bottom + spacing.sm }]}>
          <Composer conversationId={id} />
        </View>
      </KeyboardAvoidingView>

      <Overlays />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flex: 1 },
  header: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: spacing.sm,
    paddingBottom: spacing.md,
    paddingHorizontal: spacing.lg,
  },
  iconButton: { alignItems: 'center', height: 40, justifyContent: 'center', width: 40 },
  title: { flex: 1, textAlign: 'center' },
  body: { flex: 1 },
  list: { flex: 1 },
  listContent: { padding: spacing.lg },
  composerWrap: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
});
