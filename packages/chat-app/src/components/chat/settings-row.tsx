/**
 * `SettingsRow` and `SettingsSection` — the grouped-list building blocks for
 * the settings screen: an overline section header above a rounded card of
 * icon + label rows, each optionally showing a trailing value or chevron.
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
  /** Render a trailing chevron. */
  chevron?: boolean;
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
  chevron = false,
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
      {chevron ? <AppIcon color="textSecondary" name="chevron-right" size={20} /> : null}
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

/** A titled card grouping {@link SettingsRow}s, with dividers between them. */
export function SettingsSection({ title, children }: SettingsSectionProps): React.JSX.Element {
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View style={styles.section}>
      {title ? (
        <ThemedText color="textSecondary" style={styles.sectionTitle} variant="overline">
          {title}
        </ThemedText>
      ) : null}
      <View style={styles.card}>
        {rows.map((row, index) => (
          <View key={row.key ?? index}>
            {index > 0 ? <View style={styles.divider} /> : null}
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
  divider: {
    backgroundColor: colors.border,
    height: StyleSheet.hairlineWidth,
    marginLeft: spacing.xxxl + spacing.md,
  },
});
