import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createQueryClientWrapper, createTestQueryClient } from '@/test/utils/render';
import { type ChatModelOption, useChatModels } from './use-chat-models';

const replaceMock = vi.fn();

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		replace: replaceMock,
	}),
}));

/** Factory for valid `ChatModelOption` fixtures used across the suite. */
function makeModel(overrides: Partial<ChatModelOption> = {}): ChatModelOption {
	return {
		id: overrides.id ?? 'agent-sdk:anthropic/claude-sonnet-4-6',
		host: overrides.host ?? 'agent-sdk',
		vendor: overrides.vendor ?? 'anthropic',
		model: overrides.model ?? 'claude-sonnet-4-6',
		display_name: overrides.display_name ?? 'Claude Sonnet 4.6',
		short_name: overrides.short_name ?? 'Sonnet 4.6',
		description: overrides.description ?? 'Balanced reasoning model.',
	};
}

describe('useChatModels', (): void => {
	beforeEach((): void => {
		replaceMock.mockClear();
		vi.stubGlobal('fetch', vi.fn());
	});

	it('returns the catalog and a usable first entry as the default on the happy path', async (): Promise<void> => {
		const sonnet = makeModel({ id: 'agent-sdk:anthropic/claude-sonnet-4-6' });
		const gemini = makeModel({
			id: 'google-ai:google/gemini-3-flash-preview',
			host: 'google-ai',
			vendor: 'google',
			model: 'gemini-3-flash-preview',
			display_name: 'Gemini 3 Flash',
			short_name: 'Gemini 3',
		});
		vi.mocked(fetch).mockResolvedValue(Response.json({ models: [sonnet, gemini] }));

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.isLoading).toBe(false);
		});

		expect(result.current.models).toEqual([sonnet, gemini]);
		expect(result.current.default).toEqual(sonnet);
		expect(result.current.error).toBeNull();
	});

	it('defaults to the first entry regardless of catalog order', async (): Promise<void> => {
		const gemini = makeModel({
			id: 'google-ai:google/gemini-3-flash-preview',
			host: 'google-ai',
			vendor: 'google',
			model: 'gemini-3-flash-preview',
			display_name: 'Gemini 3 Flash',
			short_name: 'Gemini 3',
		});
		const sonnet = makeModel({ id: 'agent-sdk:anthropic/claude-sonnet-4-6' });
		vi.mocked(fetch).mockResolvedValue(Response.json({ models: [gemini, sonnet] }));

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.isLoading).toBe(false);
		});

		expect(result.current.default).toEqual(gemini);
	});

	it('skips a Codex SDK row when another model is available for the default', async (): Promise<void> => {
		const codex = makeModel({
			id: 'openai-codex:openai/gpt-5.5',
			host: 'openai-codex',
			vendor: 'openai',
			model: 'gpt-5.5',
			display_name: 'GPT 5.5 Codex',
			short_name: 'Codex',
		});
		const openai = makeModel({
			id: 'litellm:openai/gpt-5.1',
			host: 'litellm',
			vendor: 'openai',
			model: 'gpt-5.1',
			display_name: 'GPT 5.1',
			short_name: 'GPT 5.1',
		});
		vi.mocked(fetch).mockResolvedValue(Response.json({ models: [codex, openai] }));

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.isLoading).toBe(false);
		});

		expect(result.current.default).toEqual(openai);
	});

	it('uses Codex SDK as the default when it is the only model', async (): Promise<void> => {
		const codex = makeModel({
			id: 'openai-codex:openai/gpt-5.5',
			host: 'openai-codex',
			vendor: 'openai',
			model: 'gpt-5.5',
			display_name: 'GPT 5.5 Codex',
			short_name: 'Codex',
		});
		vi.mocked(fetch).mockResolvedValue(Response.json({ models: [codex] }));

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.isLoading).toBe(false);
		});

		expect(result.current.default).toEqual(codex);
	});

	it('returns null default when the models array is empty', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(Response.json({ models: [] }));

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.isLoading).toBe(false);
		});

		expect(result.current.models).toEqual([]);
		expect(result.current.default).toBeNull();
	});

	it('surfaces Zod validation failure as the hook error', async (): Promise<void> => {
		// `short_name` is required by the schema; omit it to trigger a parse failure.
		vi.mocked(fetch).mockResolvedValue(
			Response.json({
				models: [
					{
						id: 'agent-sdk:anthropic/claude-sonnet-4-6',
						host: 'agent-sdk',
						vendor: 'anthropic',
						model: 'claude-sonnet-4-6',
						display_name: 'Claude Sonnet 4.6',
						description: 'Balanced reasoning model.',
						// short_name intentionally missing
					},
				],
			})
		);

		const { result } = renderHook(() => useChatModels(), {
			wrapper: createQueryClientWrapper(createTestQueryClient()),
		});

		await waitFor((): void => {
			expect(result.current.error).not.toBeNull();
		});

		expect(result.current.models).toEqual([]);
		expect(result.current.default).toBeNull();
	});
});
