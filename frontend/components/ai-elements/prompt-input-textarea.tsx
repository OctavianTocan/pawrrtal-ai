/**
 * Prompt input textarea behavior.
 *
 * @fileoverview Keyboard, paste, and controlled-provider behavior for prompt input textareas.
 */

'use client';

import type { ChangeEvent, ClipboardEventHandler, ComponentProps, KeyboardEventHandler } from 'react';
import { useRef } from 'react';
import { InputGroupTextarea } from '@/components/ui/input-group';
import { useScrollEdges } from '@/hooks/use-scroll-edges';
import { cn } from '@/lib/utils';
import { useOptionalPromptInputController, usePromptInputAttachments } from './prompt-input-context';

/**
 * Handle Tab / Escape for ghost-text accept and dismiss.
 *
 * Returns `true` when the key was consumed (the textarea's keydown
 * handler should early-return). Extracted from `PromptInputTextarea`
 * so its `handleKeyDown` stays under Biome's cognitive-complexity
 * budget — the original sat at 28 once two new branches were added.
 */
function handleGhostSuggestionKey({
  event,
  ghostSuggestion,
  onAcceptSuggestion,
  onDismissSuggestion,
}: {
  event: React.KeyboardEvent<HTMLTextAreaElement>;
  ghostSuggestion: string | undefined;
  onAcceptSuggestion: (() => void) | undefined;
  onDismissSuggestion: (() => void) | undefined;
}): boolean {
  if (!ghostSuggestion) {
    return false;
  }
  if (event.key === 'Tab' && onAcceptSuggestion) {
    const ta = event.currentTarget;
    const cursorAtEnd = ta.selectionStart === ta.value.length && ta.selectionEnd === ta.value.length;
    if (cursorAtEnd) {
      event.preventDefault();
      onAcceptSuggestion();
      return true;
    }
  }
  if (event.key === 'Escape') {
    event.preventDefault();
    onDismissSuggestion?.();
    return true;
  }
  return false;
}

/** Props for the prompt input textarea. */
export type PromptInputTextareaProps = ComponentProps<typeof InputGroupTextarea> & {
  /**
   * Active ghost-text suggestion controlled by the parent (e.g. via
   * `useGhostCompletion`). The textarea itself does NOT render the
   * suggestion — it only uses the value to gate the Tab / Escape
   * keyboard interception. The overlay is rendered by the parent so
   * its layout can be co-located with the textarea's exact padding
   * and typography.
   */
  ghostSuggestion?: string;
  /**
   * Called when the user presses Tab while a ghost suggestion is
   * showing AND the caret is at the end of the current value. Tab
   * falls through to the browser's default focus-shift behavior in
   * every other case.
   */
  onAcceptSuggestion?: () => void;
  /**
   * Called when the user presses Escape while a ghost suggestion is
   * showing. Escape only fires when a suggestion is active so it
   * stays available for higher-level shortcuts otherwise.
   */
  onDismissSuggestion?: () => void;
};

/** Textarea that submits on Enter and supports pasted files. */
export const PromptInputTextarea = ({
  onChange,
  className,
  placeholder = 'What would you like to know?',
  ghostSuggestion,
  onAcceptSuggestion,
  onDismissSuggestion,
  ...props
}: PromptInputTextareaProps) => {
  const controller = useOptionalPromptInputController();
  const attachments = usePromptInputAttachments();
  // IME composition state is only read inside the keydown handler, never
  // in the render output — use a ref so toggling it during composition
  // doesn't trigger spurious re-renders of the textarea.
  const isComposingRef = useRef(false);
  // Scroll-edge fade: when the textarea has more content above/below the
  // visible area, render top/bottom mask gradients via data-attributes
  // (CSS in globals.css → `[data-prompt-textarea]`).
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { canScrollUp, canScrollDown } = useScrollEdges(textareaRef);

  const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (
      handleGhostSuggestionKey({
        event: e,
        ghostSuggestion,
        onAcceptSuggestion,
        onDismissSuggestion,
      })
    ) {
      return;
    }

    if (e.key === 'Enter') {
      if (isComposingRef.current || e.nativeEvent.isComposing) {
        return;
      }
      if (e.shiftKey) {
        return;
      }
      e.preventDefault();

      const form = e.currentTarget.form;
      const submitButton = form?.querySelector('button[type="submit"]') as HTMLButtonElement | null;
      if (submitButton?.disabled) {
        return;
      }

      form?.requestSubmit();
    }

    if (e.key === 'Backspace' && e.currentTarget.value === '' && attachments.files.length > 0) {
      e.preventDefault();
      const lastAttachment = attachments.files.at(-1);
      if (lastAttachment) {
        attachments.remove(lastAttachment.id);
      }
    }
  };

  const handlePaste: ClipboardEventHandler<HTMLTextAreaElement> = (event) => {
    const items = event.clipboardData?.items;

    if (!items) {
      return;
    }

    const files: File[] = [];

    for (const item of items) {
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) {
          files.push(file);
        }
      }
    }

    if (files.length > 0) {
      event.preventDefault();
      attachments.add(files);
    }
  };

  const controlledProps = controller
    ? {
        value: controller.textInput.value,
        onChange: (e: ChangeEvent<HTMLTextAreaElement>) => {
          controller.textInput.setInput(e.currentTarget.value);
          onChange?.(e);
        },
      }
    : {
        onChange,
      };

  return (
    <InputGroupTextarea
      className={cn('field-sizing-content max-h-48 min-h-16', className)}
      data-prompt-textarea=""
      data-scroll-down={canScrollDown ? 'true' : undefined}
      data-scroll-up={canScrollUp ? 'true' : undefined}
      name="message"
      onCompositionEnd={() => {
        isComposingRef.current = false;
      }}
      onCompositionStart={() => {
        isComposingRef.current = true;
      }}
      onKeyDown={handleKeyDown}
      onPaste={handlePaste}
      placeholder={placeholder}
      ref={textareaRef}
      {...props}
      {...controlledProps}
    />
  );
};
