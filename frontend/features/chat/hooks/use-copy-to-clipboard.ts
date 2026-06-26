'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/** How long the "Copied!" affordance stays visible after a successful copy. */
const COPY_FEEDBACK_DURATION_MS = 1500;

/** Strict result type so callers can branch on success/failure without try/catch. */
type CopyResult = { ok: true } | { ok: false; error: Error };

/**
 * Reusable clipboard hook with per-row visual feedback.
 *
 * Tracks the id of the last successfully-copied row in state so callers can
 * compare `copiedId === message.id` to flip a button's label to "Copied!"
 * Auto-clears after {@link COPY_FEEDBACK_DURATION_MS} so the affordance
 * doesn't get stuck on remount. Falls back to a hidden-textarea + execCommand
 * pipe so that Safari iframe and older-WebView contexts (where
 * `navigator.clipboard` is unavailable) still copy successfully.
 */
export function useCopyToClipboard(): {
  copy: (id: string, text: string) => Promise<CopyResult>;
  copiedId: string | null;
} {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
    },
    []
  );

  const copy = useCallback(async (id: string, text: string): Promise<CopyResult> => {
    const onSuccess = (): { ok: true } => {
      setCopiedId(id);
      if (timeoutRef.current !== null) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopiedId(null), COPY_FEEDBACK_DURATION_MS);
      return { ok: true };
    };

    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return onSuccess();
      }
    } catch {
      // Fall through to the textarea fallback below.
    }

    // Legacy fallback for WebViews / iframes without async clipboard.
    if (typeof document === 'undefined') {
      return { ok: false, error: new Error('Clipboard API unavailable') };
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      const succeeded = document.execCommand('copy');
      if (succeeded) return onSuccess();
      return { ok: false, error: new Error('execCommand("copy") failed') };
    } finally {
      document.body.removeChild(textarea);
    }
  }, []);

  return { copy, copiedId };
}
