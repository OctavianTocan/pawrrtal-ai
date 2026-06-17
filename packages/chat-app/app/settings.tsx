/**
 * Settings screen — the grouped settings list: the App / Grok / Voice / Data
 * sections, legal links, report, and sign-out, with a version footer. Matches
 * the reference settings screen, which opens directly on the Appearance group
 * (no account header — the account lives in the conversations drawer).
 */
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { SettingsRow, SettingsSection } from '@/components/chat';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { spacing } from '@/constants/spacing';
import { actions, useRun } from '@/runtime';

/** App version shown in the footer. */
const APP_VERSION = '0.1.0';

/** The settings screen. */
export default function SettingsScreen(): React.JSX.Element {
  const run = useRun();
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable
          accessibilityLabel="Close settings"
          onPress={() => run(actions.navigateBack)}
          style={styles.close}
        >
          <AppIcon name="close" size={22} />
        </Pressable>
        <ThemedText variant="title">Settings</ThemedText>
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xxl }]}
        showsVerticalScrollIndicator={false}
      >
        <SettingsSection>
          <SettingsRow chevron icon="appearance" label="Appearance" value="System" />
          <SettingsRow chevron icon="haptics" label="Haptics" />
          <SettingsRow chevron icon="widget" label="Widget" />
          <SettingsRow chevron icon="advanced" label="Advanced" />
        </SettingsSection>

        <SettingsSection title="Grok">
          <SettingsRow chevron icon="customize" label="Customize Grok" />
          <SettingsRow chevron icon="connectors" label="Connectors" />
          <SettingsRow chevron icon="skills" label="Skills" />
          <SettingsRow chevron icon="memory" label="Memory" />
          <SettingsRow chevron icon="kids" label="Kids Mode" />
        </SettingsSection>

        <SettingsSection title="Voice">
          <SettingsRow chevron icon="voice" label="Voice" value="Sal" />
        </SettingsSection>

        <SettingsSection title="Data & Information">
          <SettingsRow chevron icon="shared" label="Shared Conversations" />
          <SettingsRow chevron icon="data" label="Data Controls" />
        </SettingsSection>

        <SettingsSection>
          <SettingsRow chevron icon="licenses" label="Open Source Licenses" />
          <SettingsRow chevron icon="terms" label="Terms of Use" />
          <SettingsRow chevron icon="privacy" label="Privacy Policy" />
        </SettingsSection>

        <SettingsSection>
          <SettingsRow chevron icon="report" label="Report a Problem" />
        </SettingsSection>

        <SettingsSection>
          <SettingsRow danger icon="signout" label="Sign out" />
        </SettingsSection>

        <ThemedText centered color="textTertiary" style={styles.version} variant="caption">
          Pawrrtal Chat {APP_VERSION}
        </ThemedText>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colors.background, flex: 1 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    paddingBottom: spacing.md,
    paddingHorizontal: spacing.md,
  },
  close: { alignItems: 'center', height: 38, justifyContent: 'center', width: 38 },
  content: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  version: { marginTop: spacing.md },
});
