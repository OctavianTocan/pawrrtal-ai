'use client';

import { useEffect, useRef } from 'react';
import type { ChatMessage } from '@/lib/types';

/**
 * SessionStorage key prefix used to record which conversations had a
 * stream actively running. The prefix lets us scope the breadcrumb to
 * a single conversation id without polluting the global namespace.
 */
const RECOVERY_KEY_PREFIX = 'chat:in-flight:';

/** Build the per-conversation breadcrumb key. */
function recoveryKey(conversationId: string): string {
	return `${RECOVERY_KEY_PREFIX}${conversationId}`;
}

/** Safely read the in-flight prompt for a conversation, or null. */
function readBreadcrumb(conversationId: string): string | null {
	if (typeof window === 'undefined') return null;
	try {
		return window.sessionStorage.getItem(recoveryKey(conversationId));
	} catch {
		return null;
	}
}

/** Safely write/clear the in-flight prompt breadcrumb. */
function writeBreadcrumb(conversationId: string, value: string | null): void {
	if (typeof window === 'undefined') return;
	try {
		const key = recoveryKey(conversationId);
		if (value === null) window.sessionStorage.removeItem(key);
		else window.sessionStorage.setItem(key, value);
	} catch {
		// Private mode / quota exceeded — recovery is best-effort.
	}
}

/**
 * Detect interrupted assistant turns and offer to resume them.
 *
 * Drops a SessionStorage breadcrumb every time a turn starts and clears it
 * once the turn finishes. On mount, if a breadcrumb exists for this
 * conversation, the hook fires `onRecover(prompt)` so the container can
 * re-run the assistant turn — useful when the user navigated away or
 * refreshed mid-stream.
 *
 * The hook does nothing when `chatHistory` already shows a streaming reply
 * in progress, or when no breadcrumb is present. This keeps the recovery
 * fully passive — `onRecover` runs at most once per mount per conversation.
 */
export function useChatBackgroundRecovery({
	conversationId,
	chatHistory,
	isLoading,
	onRecover,
}: {
	conversationId: string;
	chatHistory: Array<ChatMessage>;
	isLoading: boolean;
	onRecover: (prompt: string) => void;
}): {
	/** Mark a prompt as "in flight" — call this just before starting a turn. */
	beginStream: (prompt: string) => void;
	/** Clear the breadcrumb — call this after a turn completes (success or failure). */
	endStream: () => void;
} {
	const hasCheckedRef = useRef(false);

	// One-shot recovery check on mount per conversation. Guarded with a ref so
	// the effect's deps don't accidentally re-fire it after onRecover updates
	// chat history.
	useEffect(() => {
		if (hasCheckedRef.current) return;
		hasCheckedRef.current = true;
		if (isLoading) return; // a fresh turn is already running

		const last = chatHistory[chatHistory.length - 1];
		// Only resume when the last assistant turn is missing or visibly
		// incomplete — otherwise the user just opened a finished conversation
		// and we shouldn't replay anything.
		const lastIsIncomplete =
			last?.role !== 'assistant' || last.assistant_status === 'failed' || last.content === '';
		if (!lastIsIncomplete) return;

		const queued = readBreadcrumb(conversationId);
		if (queued) onRecover(queued);
	}, [chatHistory, conversationId, isLoading, onRecover]);

	const beginStream = (prompt: string): void => writeBreadcrumb(conversationId, prompt);
	const endStream = (): void => writeBreadcrumb(conversationId, null);

	return { beginStream, endStream };
}
