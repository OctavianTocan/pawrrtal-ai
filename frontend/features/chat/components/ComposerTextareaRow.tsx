'use client';

import type * as React from 'react';
import { useCallback } from 'react';
import { PromptInputTextarea } from '@/components/ai-elements/prompt-input';
import { useGhostCompletion } from '../hooks/use-ghost-completion';

/**
 * The rotating + ghost-aware textarea block extracted out of
 * `ChatComposer` so the parent stays under the file-line and
 * cognitive-complexity budgets. The three children rendered here
 * (animated placeholder, ghost-text overlay, textarea) share the
 * exact same padding and typography contract, so co-locating them
 * in one file keeps that contract obvious and changes to one easy
 * to mirror in the others.
 */

/** Renders the rotating placeholder above the textarea. */
function AnimatedComposerPlaceholder({
  isVisible,
  text,
}: {
  isVisible: boolean;
  text: string;
}): React.JSX.Element | null {
  if (!isVisible) {
    return null;
  }

  return (
    <div
      aria-hidden="true"
      // `top-2` matches the textarea's `pt-2` so the placeholder sits on
      // the same baseline as the user's first line of text; `top-3` left
      // the placeholder a pixel off when the textarea was tightened.
      className="pointer-events-none absolute top-2 left-3 z-10 pr-6 text-[14px] text-muted-foreground/70 leading-6"
    >
      <span className="composer-placeholder-enter block" key={text}>
        {text}
      </span>
    </div>
  );
}

/**
 * Ghost-text overlay rendered BEHIND the textarea.
 *
 * Layers an invisible copy of the user's draft (`value`) to reserve
 * the exact width of the typed text, then renders the model-predicted
 * `suggestion` in a muted color in the remaining row. Padding and
 * typography MUST match the textarea byte-for-byte or the suggestion
 * drifts visually from the caret position.
 */
function GhostSuggestionOverlay({
  value,
  suggestion,
}: {
  value: string;
  suggestion: string;
}): React.JSX.Element | null {
  if (!suggestion) {
    return null;
  }
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none z-0 col-start-1 row-start-1 max-h-48 min-h-11 overflow-hidden whitespace-pre-wrap break-words px-3 pt-2 pb-1 text-[14px] leading-6"
    >
      <span className="invisible">{value}</span>
      <span className="text-muted-foreground/50">{suggestion}</span>
    </div>
  );
}

/**
 * Result type returned by {@link useComposerGhostCompletion} —
 * exported so the row prop type can reference the same shape.
 */
export interface ComposerGhostState {
  /** Current ghost suggestion (empty string when none). */
  suggestion: string;
  /** Apply the active suggestion to the composer value. */
  handleAccept: () => void;
  /** Clear the active suggestion without applying it. */
  handleDismiss: () => void;
}

/**
 * Glue between {@link useGhostCompletion} and the composer's
 * value/setter pair. Returns the suggestion plus pre-bound
 * Accept/Dismiss handlers so the composer body doesn't have to
 * repeat the same plumbing.
 */
export function useComposerGhostCompletion({
  content,
  enabled,
  onReplaceMessageContent,
}: {
  content: string;
  enabled: boolean;
  onReplaceMessageContent: (next: string) => void;
}): ComposerGhostState {
  const { suggestion, acceptSuggestion, dismissSuggestion } = useGhostCompletion({
    text: content,
    enabled,
  });
  const handleAccept = useCallback((): void => {
    const accepted = acceptSuggestion();
    if (accepted) {
      onReplaceMessageContent(content + accepted);
    }
  }, [acceptSuggestion, content, onReplaceMessageContent]);
  return { suggestion, handleAccept, handleDismiss: dismissSuggestion };
}

/** Props for {@link ComposerTextareaRow}. */
export interface ComposerTextareaRowProps {
  /** Placeholder text shown when `hasContent` is false. */
  placeholder: string;
  /** Whether the current draft has any non-whitespace content. */
  hasContent: boolean;
  /** Current draft text — controlled by the parent. */
  value: string;
  /** Native textarea change handler forwarded to the underlying control. */
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  /** Ghost-completion state from {@link useComposerGhostCompletion}. */
  ghost: ComposerGhostState;
}

/**
 * Renders the rotating placeholder, the ghost-text overlay, and the
 * textarea as one stack. Consumed by `ChatComposer`.
 */
export function ComposerTextareaRow({
  placeholder,
  hasContent,
  value,
  onChange,
  ghost,
}: ComposerTextareaRowProps): React.JSX.Element {
  return (
    <div className="relative grid w-full grid-cols-1 grid-rows-1 self-stretch">
      <AnimatedComposerPlaceholder isVisible={!hasContent} text={placeholder} />
      <GhostSuggestionOverlay suggestion={ghost.suggestion} value={value} />
      {/* `min-h-11` (44px) + `pt-2` lets a one-line draft sit
			comfortably without the textarea reading as a tall card on
			its own. The placeholder absolutely-positioned at `top-3`
			is shifted to `top-2` to track this in the parent. */}
      <PromptInputTextarea
        aria-label={placeholder}
        className="relative z-10 col-start-1 row-start-1 max-h-48 min-h-11 w-full overflow-y-auto px-3 pt-2 pb-1 text-[14px] leading-6 outline-none placeholder:text-transparent focus-visible:outline-none"
        ghostSuggestion={ghost.suggestion}
        onAcceptSuggestion={ghost.handleAccept}
        onChange={onChange}
        onDismissSuggestion={ghost.handleDismiss}
        placeholder=""
        value={value}
      />
    </div>
  );
}
