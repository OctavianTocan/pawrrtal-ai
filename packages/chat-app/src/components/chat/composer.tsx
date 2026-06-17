/**
 * `Composer` — the bottom input bar: the "Ask anything" field, the attach
 * (`+`) button, the model-tier pill, the mic, and the primary action that
 * flips between "Speak" and a send button depending on draft content.
 *
 * The draft text is local component state (so the home and thread composers
 * never share a draft). Submitting either creates a new conversation (home)
 * or appends to the current thread, dispatched through the Effect runtime.
 */
import { useRef, useState } from 'react';
import { Keyboard, StyleSheet, TextInput, View } from 'react-native';
import { Pressable } from '@/components/core/pressable';
import { ThemedText } from '@/components/core/themed-text';
import { AppIcon } from '@/components/icons/app-icon';
import { colors } from '@/constants/colors';
import { radii } from '@/constants/radii';
import { spacing } from '@/constants/spacing';
import { actions, useAppState, useCatalog, useRun } from '@/runtime';
import type { Overlay } from '@/services';

/** Props for {@link Composer}. */
export interface ComposerProps {
  /**
   * When set, submitting appends to this conversation's thread. When omitted
   * (home screen), submitting creates a new conversation and opens it.
   */
  conversationId?: string;
}

/** The bottom composer bar. */
export function Composer({ conversationId }: ComposerProps): React.JSX.Element {
  const [text, setText] = useState('');
  // Synchronous guard so a double-tap on Send (before React commits the
  // `setText('')` clear) can't dispatch the same draft twice — which would
  // create duplicate conversations / duplicate exchanges. Reset on the next
  // keystroke so the following draft can send normally.
  const submittedRef = useRef(false);
  const { homeMode, selectedTier, overlay } = useAppState();
  const catalog = useCatalog();
  const run = useRun();
  const model = catalog.models.find((m) => m.id === selectedTier);
  const modelName = model?.name ?? 'Auto';
  const modelIcon = model?.icon ?? 'auto';
  const hasDraft = text.trim().length > 0;
  const attachmentOpen = overlay === 'attachment';
  const placeholder = homeMode === 'imagine' ? 'Imagine anything' : 'Ask anything';

  const submit = (): void => {
    const trimmed = text.trim();
    if (!trimmed || submittedRef.current) return;
    submittedRef.current = true;
    run(
      conversationId
        ? actions.sendMessage(conversationId, trimmed)
        : actions.createConversation(trimmed),
    );
    setText('');
  };

  // Typing a new draft re-arms the send guard.
  const handleChangeText = (next: string): void => {
    submittedRef.current = false;
    setText(next);
  };

  // Dismiss the keyboard before presenting an overlay — otherwise on mobile
  // the keyboard stays on top of the bottom-anchored popovers/capture bar.
  const openOverlay = (overlay: Overlay): void => {
    Keyboard.dismiss();
    run(actions.setOverlay(overlay));
  };

  return (
    <View style={styles.container}>
      <TextInput
        multiline
        onChangeText={handleChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textSecondary}
        style={styles.input}
        value={text}
      />

      <View style={styles.controls}>
        <View style={styles.leftControls}>
          <Pressable
            accessibilityLabel={attachmentOpen ? 'Close attachments' : 'Add attachment'}
            onPress={() => openOverlay(attachmentOpen ? 'none' : 'attachment')}
            style={styles.circleButton}
          >
            <AppIcon name={attachmentOpen ? 'close' : 'plus'} size={20} />
          </Pressable>

          <Pressable
            accessibilityLabel="Choose model"
            onPress={() => openOverlay('model')}
            style={styles.modelPill}
          >
            <AppIcon name={modelIcon} size={16} />
            <ThemedText numberOfLines={1} style={styles.modelLabel} variant="label">
              {modelName}
            </ThemedText>
            <AppIcon color="textSecondary" name="chevron-down" size={15} />
          </Pressable>
        </View>

        <View style={styles.rightControls}>
          <Pressable
            accessibilityLabel="Dictate"
            onPress={() => openOverlay('voice')}
            style={styles.micButton}
          >
            <AppIcon color="textSecondary" name="mic" size={20} />
          </Pressable>

          {hasDraft ? (
            <Pressable accessibilityLabel="Send" onPress={submit} style={styles.sendButton}>
              <AppIcon color="onAccent" name="send" size={20} />
            </Pressable>
          ) : (
            <Pressable
              accessibilityLabel="Speak"
              onPress={() => openOverlay('voice')}
              style={styles.speakPill}
            >
              <AppIcon color="onAccent" name="waveform" size={16} />
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
    paddingTop: spacing.sm + 2,
    paddingBottom: spacing.sm,
  },
  input: {
    color: colors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
    maxHeight: 120,
    minHeight: 20,
    paddingVertical: spacing.xxs,
  },
  controls: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  // Allow the left group (and the model pill within it) to shrink so the row
  // never overflows / clips controls on narrow (~320dp) phones.
  leftControls: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: spacing.sm,
    minWidth: 0,
  },
  rightControls: { alignItems: 'center', flexDirection: 'row', flexShrink: 0, gap: spacing.sm },
  circleButton: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  modelPill: {
    alignItems: 'center',
    backgroundColor: colors.surfaceElevated,
    borderRadius: radii.full,
    flexDirection: 'row',
    flexShrink: 1,
    gap: spacing.xs,
    height: 32,
    minWidth: 0,
    paddingHorizontal: spacing.md,
  },
  modelLabel: { flexShrink: 1, marginHorizontal: spacing.xxs },
  micButton: {
    alignItems: 'center',
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: radii.full,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  speakPill: {
    alignItems: 'center',
    backgroundColor: colors.accent,
    borderRadius: radii.full,
    flexDirection: 'row',
    gap: spacing.xs,
    height: 34,
    paddingHorizontal: spacing.md + 2,
  },
  speakLabel: { marginLeft: spacing.xxs },
});
