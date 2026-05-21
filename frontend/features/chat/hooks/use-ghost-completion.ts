'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';

/**
 * Delay between the last keystroke and the autocomplete fetch.
 *
 * 200ms is the standard window for IDE-style ghost-text (Copilot, Cursor)
 * — short enough to feel responsive, long enough that fast typists never
 * trigger a fetch they're about to invalidate two characters later.
 */
const DEBOUNCE_MS = 200;

/**
 * Minimum prefix length before we ask the backend for a suggestion.
 *
 * Matches the backend's ``MIN_PREFIX_CHARS`` so the frontend doesn't
 * make round-trips the backend will short-circuit anyway.
 */
const MIN_PREFIX_CHARS = 3;

/**
 * Soft cap on in-memory cache size. A chat composer rarely sees more
 * than a few dozen distinct prefixes per session, but a long editing
 * session can drift higher — bound the map so we don't leak.
 */
const CACHE_MAX_ENTRIES = 100;

interface AutocompleteResponseBody {
	suggestion: string;
}

interface UseGhostCompletionArgs {
	/** Current draft text in the composer. */
	text: string;
	/** Disable the hook (e.g. while a message is streaming). */
	enabled: boolean;
}

interface UseGhostCompletionResult {
	/** Predicted continuation of ``text``, or empty when none is available. */
	suggestion: string;
	/**
	 * Pop the current suggestion and return it.
	 *
	 * Returns ``null`` when no suggestion is active. The caller is
	 * responsible for appending the returned text to the composer's value.
	 */
	acceptSuggestion: () => string | null;
	/** Clear the current suggestion without accepting it. */
	dismissSuggestion: () => void;
}

/**
 * IDE-style ghost-text autocomplete for the chat composer.
 *
 * Fetches a short continuation prediction from
 * ``/api/v1/completions/autocomplete`` whenever ``text`` changes,
 * debounced by ``DEBOUNCE_MS``. In-flight requests are aborted when
 * the text changes again; recent prefixes are cached in memory to
 * cover backspace / retype loops without re-hitting the backend.
 *
 * Failure modes are intentional no-ops: a network error, timeout, or
 * stale response collapses to an empty suggestion so the UI never
 * renders broken ghost text.
 *
 * @remarks
 * This hook reaches for ``useEffect`` directly (vs. ``useQuery``) because
 * autocomplete needs debounce + AbortController + tiny prefix-keyed cache
 * — a combination TanStack Query doesn't compose cleanly. The effect's
 * only job is to schedule a debounced fetch; it doesn't sync derived state.
 */
export function useGhostCompletion({
	text,
	enabled,
}: UseGhostCompletionArgs): UseGhostCompletionResult {
	const [suggestion, setSuggestion] = useState('');
	const controllerRef = useRef<AbortController | null>(null);
	const cacheRef = useRef<Map<string, string>>(new Map());
	const latestRequestedRef = useRef<string>('');

	const fetchSuggestion = useCallback(async (prefix: string): Promise<void> => {
		// Abort the previous in-flight call so its result can never
		// overwrite a newer one. We create a fresh controller per
		// request — sharing a controller would cancel sibling fetches
		// after the first abort.
		controllerRef.current?.abort();
		const controller = new AbortController();
		controllerRef.current = controller;
		latestRequestedRef.current = prefix;

		try {
			const res = await apiFetch('/api/v1/completions/autocomplete', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ text: prefix }),
				signal: controller.signal,
			});
			if (!res.ok) return;

			const body = (await res.json()) as AutocompleteResponseBody;
			if (typeof body?.suggestion !== 'string') return;

			// Discard if the user typed past this prefix while the
			// request was in flight — a stale suggestion would render
			// the wrong continuation against the current value.
			if (latestRequestedRef.current !== prefix) return;

			cacheRef.current.set(prefix, body.suggestion);
			if (cacheRef.current.size > CACHE_MAX_ENTRIES) {
				const oldestKey = cacheRef.current.keys().next().value;
				if (oldestKey !== undefined) cacheRef.current.delete(oldestKey);
			}
			setSuggestion(body.suggestion);
		} catch (err) {
			// AbortError is the expected signal that we cancelled the
			// fetch — silently drop it. Other errors leave the
			// suggestion empty so the UI degrades gracefully.
			if (err instanceof DOMException && err.name === 'AbortError') return;
		}
	}, []);

	useEffect(() => {
		if (!enabled) {
			setSuggestion('');
			return;
		}

		if (text.trimEnd().length < MIN_PREFIX_CHARS) {
			setSuggestion('');
			return;
		}

		const cached = cacheRef.current.get(text);
		if (cached !== undefined) {
			setSuggestion(cached);
			return;
		}

		const handle = window.setTimeout(() => {
			void fetchSuggestion(text);
		}, DEBOUNCE_MS);

		return () => {
			window.clearTimeout(handle);
		};
	}, [text, enabled, fetchSuggestion]);

	// Cancel any in-flight request when the component unmounts so a
	// late response can't try to setState on a dead component.
	useEffect(
		() => () => {
			controllerRef.current?.abort();
		},
		[]
	);

	const acceptSuggestion = useCallback((): string | null => {
		if (!suggestion) return null;
		const accepted = suggestion;
		setSuggestion('');
		return accepted;
	}, [suggestion]);

	const dismissSuggestion = useCallback((): void => {
		setSuggestion('');
	}, []);

	return { suggestion, acceptSuggestion, dismissSuggestion };
}
