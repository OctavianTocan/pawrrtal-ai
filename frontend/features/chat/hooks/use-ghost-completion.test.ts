import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useGhostCompletion } from './use-ghost-completion';

const { mockRouter } = vi.hoisted(() => ({
	mockRouter: {
		replace: vi.fn(),
		push: vi.fn(),
		back: vi.fn(),
		forward: vi.fn(),
		refresh: vi.fn(),
		prefetch: vi.fn(),
	},
}));

vi.mock('next/navigation', () => ({
	useRouter: () => mockRouter,
	usePathname: () => '/',
	useSearchParams: () => new URLSearchParams(),
}));

/**
 * Helper: build a `Response` that resolves with the given suggestion.
 *
 * `apiFetch` is a thin wrapper around `fetch` — stubbing the global
 * gives the hook a real Response to consume.
 */
function suggestionResponse(suggestion: string): Response {
	return new Response(JSON.stringify({ suggestion }), {
		status: 200,
		headers: { 'Content-Type': 'application/json' },
	});
}

/**
 * The hook debounces fetches by 200ms. Tests use real timers to keep
 * `waitFor` (which polls via real `setTimeout`) usable; this slightly
 * lengthens the suite but keeps assertions deterministic.
 */
const DEBOUNCE_WAIT_MS = 350;

describe('useGhostCompletion', (): void => {
	beforeEach((): void => {
		vi.stubGlobal('fetch', vi.fn());
	});

	afterEach((): void => {
		vi.unstubAllGlobals();
	});

	it('starts with no suggestion', (): void => {
		const { result } = renderHook(() => useGhostCompletion({ text: '', enabled: true }));
		expect(result.current.suggestion).toBe('');
	});

	it('skips the fetch for prefixes shorter than the minimum', async (): Promise<void> => {
		const fetchMock = vi.mocked(fetch).mockResolvedValue(suggestionResponse('nope'));

		const { result } = renderHook(() => useGhostCompletion({ text: 'hi', enabled: true }));

		await new Promise((resolve) => setTimeout(resolve, DEBOUNCE_WAIT_MS));

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.current.suggestion).toBe('');
	});

	it('fetches a suggestion after the debounce window elapses', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(suggestionResponse('there friend'));

		const { result } = renderHook(() => useGhostCompletion({ text: 'hello ', enabled: true }));

		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe('there friend');
			},
			{ timeout: 2000 }
		);
	});

	it('does not fetch when disabled', async (): Promise<void> => {
		const fetchMock = vi.mocked(fetch).mockResolvedValue(suggestionResponse('x'));

		renderHook(() => useGhostCompletion({ text: 'hello world', enabled: false }));

		await new Promise((resolve) => setTimeout(resolve, DEBOUNCE_WAIT_MS));

		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('clears the suggestion when disabled mid-session', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(suggestionResponse('world'));

		const { result, rerender } = renderHook(
			({ enabled }: { enabled: boolean }) => useGhostCompletion({ text: 'hello ', enabled }),
			{ initialProps: { enabled: true } }
		);

		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe('world');
			},
			{ timeout: 2000 }
		);

		rerender({ enabled: false });
		expect(result.current.suggestion).toBe('');
	});

	it('returns and clears the suggestion when accepted', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(suggestionResponse(' world'));

		const { result } = renderHook(() => useGhostCompletion({ text: 'hello', enabled: true }));

		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe(' world');
			},
			{ timeout: 2000 }
		);

		let accepted: string | null = null;
		act((): void => {
			accepted = result.current.acceptSuggestion();
		});

		expect(accepted).toBe(' world');
		expect(result.current.suggestion).toBe('');
	});

	it('returns null when accepting with no active suggestion', (): void => {
		const { result } = renderHook(() => useGhostCompletion({ text: '', enabled: true }));

		let accepted: string | null = ' not-null-sentinel';
		act((): void => {
			accepted = result.current.acceptSuggestion();
		});
		expect(accepted).toBeNull();
	});

	it('clears the suggestion on dismiss', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(suggestionResponse('there'));

		const { result } = renderHook(() => useGhostCompletion({ text: 'hello', enabled: true }));

		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe('there');
			},
			{ timeout: 2000 }
		);

		act((): void => {
			result.current.dismissSuggestion();
		});
		expect(result.current.suggestion).toBe('');
	});

	it('serves a cached suggestion without re-fetching the same prefix', async (): Promise<void> => {
		const fetchMock = vi.mocked(fetch).mockResolvedValue(suggestionResponse('there'));

		const { result, rerender } = renderHook(
			({ text }: { text: string }) => useGhostCompletion({ text, enabled: true }),
			{ initialProps: { text: 'hello' } }
		);

		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe('there');
			},
			{ timeout: 2000 }
		);

		rerender({ text: 'goodbye' });
		await waitFor(
			(): void => {
				expect(fetchMock).toHaveBeenCalledTimes(2);
			},
			{ timeout: 2000 }
		);

		const callsAfterSecondFetch = fetchMock.mock.calls.length;
		rerender({ text: 'hello' });
		await new Promise((resolve) => setTimeout(resolve, DEBOUNCE_WAIT_MS));

		expect(fetchMock).toHaveBeenCalledTimes(callsAfterSecondFetch);
		expect(result.current.suggestion).toBe('there');
	});

	it('discards stale responses arriving after the user types more', async (): Promise<void> => {
		let resolveFirst!: (response: Response) => void;
		const firstResponse = new Promise<Response>((resolve) => {
			resolveFirst = resolve;
		});
		const fetchMock = vi
			.mocked(fetch)
			.mockReturnValueOnce(firstResponse)
			.mockResolvedValue(suggestionResponse('newer'));

		const { result, rerender } = renderHook(
			({ text }: { text: string }) => useGhostCompletion({ text, enabled: true }),
			{ initialProps: { text: 'hello' } }
		);

		// Wait until the first debounced fetch fires (it never resolves
		// — we hold its promise open).
		await waitFor(
			(): void => {
				expect(fetchMock).toHaveBeenCalledTimes(1);
			},
			{ timeout: 2000 }
		);

		rerender({ text: 'hello world' });
		await waitFor(
			(): void => {
				expect(result.current.suggestion).toBe('newer');
			},
			{ timeout: 2000 }
		);

		// Release the original (stale) response. The hook must ignore
		// it because the user has moved past 'hello'.
		resolveFirst(suggestionResponse('older'));
		await new Promise((resolve) => setTimeout(resolve, 50));

		expect(result.current.suggestion).toBe('newer');
	});

	it('does not surface a suggestion when the backend returns a non-OK response', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(new Response('boom', { status: 500 }));

		const { result } = renderHook(() => useGhostCompletion({ text: 'hello', enabled: true }));

		await new Promise((resolve) => setTimeout(resolve, DEBOUNCE_WAIT_MS));
		expect(result.current.suggestion).toBe('');
	});

	it('does not surface a suggestion when the fetch is aborted', async (): Promise<void> => {
		vi.mocked(fetch).mockImplementation(
			(): Promise<Response> => Promise.reject(new DOMException('Aborted', 'AbortError'))
		);

		const { result } = renderHook(() => useGhostCompletion({ text: 'hello', enabled: true }));

		await new Promise((resolve) => setTimeout(resolve, DEBOUNCE_WAIT_MS));
		expect(result.current.suggestion).toBe('');
	});
});
