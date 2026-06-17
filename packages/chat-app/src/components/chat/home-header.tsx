/**
 * `HomeHeader` — the top bar on the home screen: the drawer button (left), the
 * "Ask" / "Imagine" segmented tabs (center, with an active underline), and the
 * incognito toggle (right).
 */
import { StyleSheet, View } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import type { HomeMode } from '@/domain';
import { actions, useAppState, useRun } from '@/runtime';

/** The two home tabs, in display order. */
const TABS: readonly { readonly mode: HomeMode; readonly label: string }[] = [
  { mode: 'ask', label: 'Ask' },
  { mode: 'imagine', label: 'Imagine' },
];

/** The home screen's top navigation bar. */
export function HomeHeader(): React.JSX.Element {
  const { homeMode } = useAppState();
  const run = useRun();

  return (
    <View style={styles.container}>
      <Pressable
        accessibilityLabel="Open conversations"
        onPress={() => run(actions.navigatePush('/conversations'))}
        style={styles.iconButton}
      >
        <AppIcon name="menu" size={23} />
      </Pressable>

      <View style={styles.tabs}>
        {TABS.map((tab) => {
          const active = tab.mode === homeMode;
          return (
            <Pressable
              accessibilityLabel={tab.label}
              key={tab.mode}
              onPress={() => run(actions.setHomeMode(tab.mode))}
              style={styles.tab}
            >
              <ThemedText color={active ? 'textPrimary' : 'textSecondary'} variant="titleLarge">
                {tab.label}
              </ThemedText>
              {active ? <View style={styles.activeUnderline} /> : null}
            </Pressable>
          );
        })}
      </View>

      <Pressable accessibilityLabel="Private chat" style={styles.iconButton}>
        <AppIcon name="incognito" size={22} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  iconButton: {
    alignItems: 'center',
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  tabs: { alignItems: 'center', flexDirection: 'row', gap: spacing.md },
  tab: { alignItems: 'center', gap: spacing.xxs },
  activeUnderline: {
    backgroundColor: colors.textPrimary,
    borderRadius: radii.full,
    height: 2.5,
    width: 20,
  },
});
