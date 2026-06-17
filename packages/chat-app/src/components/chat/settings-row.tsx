/**
 * `SettingsRow` and `SettingsSection` — the grouped-list building blocks for
 * the settings screen: an overline section header above a stack of individual
 * rounded icon + label cards, each optionally showing a trailing value or a
 * toggle. The reference renders each row as its own rounded card with a small
 * gap between them (not a single container split by dividers) and shows no
 * trailing chevrons — only the occasional value subtitle or a toggle.
 */
import { Children, isValidElement, type ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon, type IconName } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';

/** Props for {@link SettingsRow}. */
export interface SettingsRowProps {
  /** Leading icon. */
  icon: IconName;
  /** Row label. */
  label: string;
  /** Optional trailing value (e.g. "System", "Sal"). */
  value?: string;
  /** Render a trailing toggle (shown in the off state — UI-only). */
  toggle?: boolean;
  /** Style the row as destructive (red). */
  danger?: boolean;
  /** Press handler. */
  onPress?: () => void;
}

/** A single settings list row. */
export function SettingsRow({
  icon,
  label,
  value,
  toggle = false,
  danger = false,
  onPress,
}: SettingsRowProps): React.JSX.Element {
  return (
    <Pressable accessibilityLabel={label} onPress={onPress} style={styles.row}>
      <AppIcon color={danger ? 'danger' : 'textPrimary'} name={icon} size={20} />
      <View style={styles.labelArea}>
        <ThemedText color={danger ? 'danger' : 'textPrimary'} variant="bodyStrong">
          {label}
        </ThemedText>
        {value ? (
          <ThemedText color="textSecondary" variant="caption">
            {value}
          </ThemedText>
        ) : null}
      </View>
      {toggle ? (
        <View style={styles.toggleTrack}>
          <View style={styles.toggleKnob} />
        </View>
      ) : null}
    </Pressable>
  );
}

/** Props for {@link SettingsSection}. */
export interface SettingsSectionProps {
  /** Optional overline header (e.g. "App", "Grok"). */
  title?: string;
  /** {@link SettingsRow} children. */
  children: ReactNode;
}

/** A titled group of individual rounded {@link SettingsRow} cards. */
export function SettingsSection({ title, children }: SettingsSectionProps): React.JSX.Element {
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View style={styles.section}>
      {title ? (
        <ThemedText color="textSecondary" style={styles.sectionTitle} variant="overline">
          {title}
        </ThemedText>
      ) : null}
      <View style={styles.rows}>
        {rows.map((row, index) => (
          <View key={row.key ?? index} style={styles.card}>
            {row}
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.xs, marginBottom: spacing.lg },
  sectionTitle: { marginBottom: spacing.sm, marginLeft: spacing.xs, textTransform: 'none' },
  // Each row is its own rounded card; a small gap separates them (the
  // reference stacks discrete cards rather than a single divided container).
  rows: { gap: spacing.sm },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    overflow: 'hidden',
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md + 1,
  },
  labelArea: { flex: 1, gap: 1 },
  // Off-state toggle: a dark track with a light knob nudged to the left edge,
  // matching the reference's Kids Mode switch.
  toggleTrack: {
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 28,
    justifyContent: 'center',
    paddingHorizontal: 3,
    width: 48,
  },
  toggleKnob: {
    backgroundColor: colors.textSecondary,
    borderRadius: radii.full,
    height: 22,
    width: 22,
  },
});
