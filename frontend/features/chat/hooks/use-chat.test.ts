import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatStreamEvent } from '../types';
import { useChat } from './use-chat';

const replaceMock = vi.fn();

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		replace: replaceMock,
	}),
}));

function createStreamResponse(chunks: string[]): Response {
	const encoder = new TextEncoder();

	return new Response(
		new ReadableStream({
			start(controller): void {
				for (const chunk of chunks) {
					controller.enqueue(encoder.encode(chunk));
				}
				controller.close();
			},
		}),
		{
			headers: {
				'content-type': 'text/event-stream',
			},
		}
	);
}

async function collectStream(
	stream: AsyncGenerator<ChatStreamEvent>
): Promise<Array<ChatStreamEvent>> {
	const events: Array<ChatStreamEvent> = [];

	for await (const event of stream) {
		events.push(event);
	}

	return events;
}

describe('useChat', (): void => {
	beforeEach((): void => {
		replaceMock.mockClear();
		vi.stubGlobal('fetch', vi.fn());
	});

	it('posts to the versioned chat endpoint and yields delta events', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(
			createStreamResponse([
				'data: {"type":"delta","content":"Hel"}\n\n',
				'data: {"type":"delta","content":"lo"}\n\n',
				'data: [DONE]\n\n',
			])
		);

		const { result } = renderHook(() => useChat());

		await expect(
			collectStream(
				result.current.streamMessage(
					'Hi',
					'conversation-1',
					'google-ai:google/gemini-3-flash-preview',
					'high'
				)
			)
		).resolves.toEqual([
			{ type: 'delta', content: 'Hel' },
			{ type: 'delta', content: 'lo' },
		]);

		expect(fetch).toHaveBeenCalledWith('http://localhost:8000/api/v1/chat', {
			method: 'POST',
			body: JSON.stringify({
				question: 'Hi',
				conversation_id: 'conversation-1',
				model_id: 'google-ai:google/gemini-3-flash-preview',
				reasoning_effort: 'high',
			}),
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream',
			},
			credentials: 'include',
			cache: 'no-store',
		});
	});

	it('buffers SSE frames split across network chunks', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(
			createStreamResponse([
				'data: {"type":"delta","',
				'content":"Split"}\n\n',
				'data: [DONE]\n\n',
			])
		);

		const { result } = renderHook(() => useChat());

		await expect(
			collectStream(
				result.current.streamMessage(
					'Hi',
					'conversation-1',
					'google-ai:google/gemini-3-flash-preview',
					'medium'
				)
			)
		).resolves.toEqual([{ type: 'delta', content: 'Split' }]);
	});

	it('yields thinking, tool_use, and tool_result events alongside deltas', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(
			createStreamResponse([
				'data: {"type":"thinking","content":"Let me search..."}\n\n',
				'data: {"type":"tool_use","tool_use_id":"t1","name":"web_search","input":{"q":"foo"},"display":{"present":"Searching the web for foo"}}\n\n',
				'data: {"type":"tool_result","tool_use_id":"t1","content":"result body"}\n\n',
				'data: {"type":"delta","content":"Done."}\n\n',
				'data: [DONE]\n\n',
			])
		);

		const { result } = renderHook(() => useChat());

		await expect(
			collectStream(
				result.current.streamMessage(
					'Hi',
					'conversation-1',
					'agent-sdk:anthropic/claude-sonnet-4-6',
					'extra-high'
				)
			)
		).resolves.toEqual([
			{ type: 'thinking', content: 'Let me search...' },
			{
				type: 'tool_use',
				tool_use_id: 't1',
				name: 'web_search',
				input: { q: 'foo' },
				display: { present: 'Searching the web for foo' },
			},
			{ type: 'tool_result', tool_use_id: 't1', content: 'result body' },
			{ type: 'delta', content: 'Done.' },
		]);
	});

	it('throws backend stream error events instead of thinking forever', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(
			createStreamResponse([
				'data: {"type":"error","content":"Claude CLI failed: missing auth"}\n\n',
				'data: [DONE]\n\n',
			])
		);

		const { result } = renderHook(() => useChat());

		await expect(
			collectStream(
				result.current.streamMessage(
					'Hi',
					'conversation-1',
					'agent-sdk:anthropic/claude-sonnet-4-6',
					'low'
				)
			)
		).rejects.toThrow('Claude CLI failed: missing auth');
	});

	it('ignores frames with unknown event types', async (): Promise<void> => {
		vi.mocked(fetch).mockResolvedValue(
			createStreamResponse([
				'data: {"type":"unknown","content":"ignore me"}\n\n',
				'data: {"type":"delta","content":"hi"}\n\n',
				'data: [DONE]\n\n',
			])
		);

		const { result } = renderHook(() => useChat());

		await expect(
			collectStream(
				result.current.streamMessage(
					'Hi',
					'conversation-1',
					'google-ai:google/gemini-3-flash-preview',
					'medium'
				)
			)
		).resolves.toEqual([{ type: 'delta', content: 'hi' }]);
	});
});
