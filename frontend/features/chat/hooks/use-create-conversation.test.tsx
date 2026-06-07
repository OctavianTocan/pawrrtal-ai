import { QueryClient } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Conversation } from '@/lib/types';
import { createQueryClientWrapper, createTestQueryClient } from '@/test/utils/render';
import { useCreateConversation } from './use-create-conversation';

const replaceMock = vi.fn();

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		replace: replaceMock,
	}),
}));

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
	return {
		id: overrides.id ?? 'conversation-1',
		user_id: overrides.user_id ?? 'user-1',
		title: overrides.title ?? 'New chat',
		created_at: overrides.created_at ?? '2026-05-03T12:00:00.000Z',
		updated_at: overrides.updated_at ?? '2026-05-03T12:00:00.000Z',
		is_archived: overrides.is_archived ?? false,
		is_flagged: overrides.is_flagged ?? false,
		is_unread: overrides.is_unread ?? false,
		status: overrides.status ?? null,
	};
}

describe('useCreateConversation', (): void => {
	beforeEach((): void => {
		replaceMock.mockClear();
		vi.stubGlobal('fetch', vi.fn());
	});

	it('creates a conversation with the client-reserved id', async (): Promise<void> => {
		const conversation = makeConversation({ id: 'client-reserved-id', title: 'Hello' });
		const queryClient = createTestQueryClient();
		vi.mocked(fetch).mockResolvedValue(Response.json(conversation));

		const { result } = renderHook(() => useCreateConversation('client-reserved-id'), {
			wrapper: createQueryClientWrapper(queryClient),
		});

		result.current.mutate({ title: 'Hello' });

		await waitFor((): void => {
			expect(result.current.isSuccess).toBe(true);
		});

		expect(fetch).toHaveBeenCalledWith('/api/v1/conversations/client-reserved-id', {
			method: 'POST',
			body: JSON.stringify({ title: 'Hello' }),
			headers: {
				'content-type': 'application/json',
			},
			credentials: 'include',
			cache: 'no-store',
		});
	});

	it('upserts the returned conversation at the head of the cached sidebar list', async (): Promise<void> => {
		const queryClient = new QueryClient({
			defaultOptions: {
				queries: { retry: false },
				mutations: { retry: false },
			},
		});
		const staleConversation = makeConversation({ id: 'existing', title: 'Old title' });
		const untouchedConversation = makeConversation({ id: 'other', title: 'Other' });
		const returnedConversation = makeConversation({ id: 'existing', title: 'Fresh title' });

		queryClient.setQueryData<Conversation[]>(
			['conversations'],
			[staleConversation, untouchedConversation]
		);
		vi.mocked(fetch).mockResolvedValue(Response.json(returnedConversation));

		const { result } = renderHook(() => useCreateConversation('existing'), {
			wrapper: createQueryClientWrapper(queryClient),
		});

		result.current.mutate({ title: 'Fresh title' });

		await waitFor((): void => {
			expect(result.current.isSuccess).toBe(true);
		});

		expect(queryClient.getQueryData<Conversation[]>(['conversations'])).toEqual([
			returnedConversation,
			untouchedConversation,
		]);
	});
});
