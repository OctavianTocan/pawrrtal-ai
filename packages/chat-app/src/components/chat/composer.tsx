/**
 * `Composer` — the bottom input bar: the "Ask anything" field, the attach
 * (`+`) button, the model-tier pill, the mic, and the primary action that
 * flips between "Speak" and a send button depending on draft content.
 *
 * All state (draft text, selected tier, which overlay is open) lives in the
 * Effect store; this component reads it via `useAppState` and dispatches
 * mutations via `useRun`.
 */
import { StyleSheet, TextInput, View } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useAppState, useCatalog, useRun } from '@/runtime';

/** The bottom composer bar. */
export function Composer(): React.JSX.Element {
  const { composerText, selectedTier, overlay } = useAppState();
  const catalog = useCatalog();
  const run = useRun();
  const model = catalog.models.find((m) => m.id === selectedTier);
  const modelName = model?.name ?? 'Auto';
  const modelIcon = model?.icon ?? 'auto';
  const hasDraft = composerText.trim().length > 0;
  const attachmentOpen = overlay === 'attachment';

  return (
    <View style={styles.container}>
      <TextInput
        multiline
        onChangeText={(text) => run(actions.setComposerText(text))}
        placeholder="Ask anything"
        placeholderTextColor={colors.textSecondary}
        style={styles.input}
        value={composerText}
      />

      <View style={styles.controls}>
        <View style={styles.leftControls}>
          <Pressable
            accessibilityLabel={attachmentOpen ? 'Close attachments' : 'Add attachment'}
            onPress={() => run(actions.setOverlay(attachmentOpen ? 'none' : 'attachment'))}
            style={styles.circleButton}
          >
            <AppIcon name={attachmentOpen ? 'close' : 'plus'} size={22} />
          </Pressable>

          <Pressable
            accessibilityLabel="Choose model"
            onPress={() => run(actions.setOverlay('model'))}
            style={styles.modelPill}
          >
            <AppIcon name={modelIcon as never} size={18} />
            <ThemedText style={styles.modelLabel} variant="label">
              {modelName}
            </ThemedText>
            <AppIcon color="textSecondary" name="chevron-down" size={16} />
          </Pressable>
        </View>

        <View style={styles.rightControls}>
          <Pressable
            accessibilityLabel="Dictate"
            onPress={() => run(actions.setOverlay('voice'))}
            style={styles.micButton}
          >
            <AppIcon color="textSecondary" name="mic" size={22} />
          </Pressable>

          {hasDraft ? (
            <Pressable accessibilityLabel="Send" style={styles.sendButton}>
              <AppIcon color="onAccent" name="send" size={22} />
            </Pressable>
          ) : (
            <Pressable
              accessibilityLabel="Speak"
              onPress={() => run(actions.setOverlay('voice'))}
              style={styles.speakPill}
            >
              <AppIcon color="onAccent" name="waveform" size={18} />
              <ThemedText color="onAccent" style={styles.speakLabel} variant="label">
                Speak
              </ThemedText>
            </Pressable>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radii.xl,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  input: {
    color: colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    maxHeight: 120,
    minHeight: 24,
    paddingVertical: spacing.xs,
  },
  controls: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  leftControls: { alignItems: 'center', flexDirection: 'row', gap: spacing.sm },
  rightControls: { alignItems: 'center', flexDirection: 'row', gap: spacing.sm },
  circleButton: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  modelPill: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    flexDirection: 'row',
    gap: spacing.xs,
    height: 36,
    paddingHorizontal: spacing.md,
  },
  modelLabel: { marginHorizontal: spacing.xxs },
  micButton: {
    alignItems: 'center',
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: radii.full,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  speakPill: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: radii.full,
    flexDirection: 'row',
    gap: spacing.xs,
    height: 40,
    paddingHorizontal: spacing.lg,
  },
  speakLabel: { marginLeft: spacing.xxs },
});
