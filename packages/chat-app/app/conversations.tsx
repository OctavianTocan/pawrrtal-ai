/**
 * Conversations screen — the history drawer: an account header, the Tasks
 * shortcut, the titled conversation list, and a footer with search, settings,
 * and a compose button.
 */
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ConversationRow } from '@/components/chat';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { Logo } from '@/components/icons/logo';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { SEED_ACCOUNT } from '@/data/seed';
import { actions, useCatalog, useRun } from '@/runtime';

/** The conversation history drawer screen. */
export default function ConversationsScreen(): React.JSX.Element {
  const catalog = useCatalog();
  const run = useRun();
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.account}>
          <View style={styles.avatar}>
            <Logo color={colors.textPrimary} size={26} />
          </View>
          <View style={styles.accountText}>
            <ThemedText variant="title">{SEED_ACCOUNT.name}</ThemedText>
            <ThemedText color="textSecondary" variant="caption">
              {SEED_ACCOUNT.plan}
            </ThemedText>
          </View>
        </View>
        <Pressable
          accessibilityLabel="Close"
          onPress={() => run(actions.navigateBack)}
          style={styles.collapse}
        >
          <AppIcon color="textSecondary" name="chevron-back" size={22} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        style={styles.list}
      >
        <Pressable accessibilityLabel="Tasks" style={styles.tasks}>
          <AppIcon name="tasks" size={22} />
          <ThemedText variant="bodyStrong">Tasks</ThemedText>
        </Pressable>

        <ThemedText color="textSecondary" style={styles.sectionLabel} variant="overline">
          Conversations
        </ThemedText>

        {catalog.conversations.map((conversation) => (
          <ConversationRow conversation={conversation} key={conversation.id} />
        ))}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.sm }]}>
        <View style={styles.search}>
          <AppIcon color="textSecondary" name="search" size={20} />
          <TextInput
            placeholder="Search"
            placeholderTextColor={colors.textSecondary}
            style={styles.searchInput}
          />
        </View>
        <Pressable
          accessibilityLabel="Settings"
          onPress={() => run(actions.navigatePush('/settings'))}
          style={styles.footerButton}
        >
          <AppIcon name="settings" size={22} />
        </Pressable>
        <Pressable
          accessibilityLabel="New conversation"
          onPress={() => run(actions.navigateBack)}
          style={styles.footerButton}
        >
          <AppIcon name="compose" size={22} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flex: 1 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  account: { alignItems: 'center', flexDirection: 'row', gap: spacing.md },
  avatar: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  accountText: { gap: spacing.xxs },
  collapse: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  list: { flex: 1 },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
  tasks: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    flexDirection: 'row',
    gap: spacing.md,
    marginBottom: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  sectionLabel: { marginBottom: spacing.xs, textTransform: 'none' },
  footer: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  search: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radii.full,
    flex: 1,
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  searchInput: { color: colors.textPrimary, flex: 1, fontSize: 15, padding: 0 },
  footerButton: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radii.full,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
});
