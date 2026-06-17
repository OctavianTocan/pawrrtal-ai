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
          <SettingsRow icon="appearance" label="Appearance" value="System" />
          <SettingsRow icon="haptics" label="Haptics" />
          <SettingsRow icon="widget" label="Widget" />
          <SettingsRow icon="advanced" label="Advanced" />
        </SettingsSection>

        <SettingsSection title="Grok">
          <SettingsRow icon="customize" label="Customize Grok" />
          <SettingsRow icon="connectors" label="Connectors" />
          <SettingsRow icon="skills" label="Skills" />
          <SettingsRow icon="memory" label="Memory" />
        </SettingsSection>

        {/* Kids Mode + NSFW sit in their own untitled group below Grok in the
            reference, not as trailing rows of the Grok group. */}
        <SettingsSection>
          <SettingsRow icon="kids" label="Kids Mode" toggle />
          <SettingsRow icon="nsfw" label="NSFW Preferences" />
        </SettingsSection>

        <SettingsSection title="Voice">
          <SettingsRow icon="voice" label="Voice" value="Sal" />
        </SettingsSection>

        <SettingsSection title="Data & Information">
          <SettingsRow icon="shared" label="Shared Conversations" />
          <SettingsRow icon="data" label="Data Controls" />
        </SettingsSection>

        <SettingsSection>
          <SettingsRow icon="licenses" label="Open Source Licenses" />
          <SettingsRow icon="terms" label="Terms of Use" />
          <SettingsRow icon="privacy" label="Privacy Policy" />
        </SettingsSection>

        <SettingsSection>
          <SettingsRow icon="report" label="Report a Problem" />
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
