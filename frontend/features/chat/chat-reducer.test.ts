import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '@/lib/types';
import { applyChatEvent, updateLastAssistantMessage } from './chat-reducer';
import type { ChatStreamEvent } from './types';

function blankAssistant(): ChatMessage {
	return { role: 'assistant', content: '' };
}

describe('applyChatEvent', () => {
	it('appends delta content and stamps thinking_started_at on first event', () => {
		const initial = blankAssistant();
		const event: ChatStreamEvent = { type: 'delta', content: 'Hello' };
		const next = applyChatEvent(initial, event);

		expect(next.content).toBe('Hello');
		expect(next.assistant_status).toBe('streaming');
		expect(typeof next.thinking_started_at).toBe('number');
	});

	it('coalesces consecutive thinking events into a single timeline entry', () => {
		let msg = blankAssistant();
		msg = applyChatEvent(msg, { type: 'thinking', content: 'Let me ' });
		msg = applyChatEvent(msg, { type: 'thinking', content: 'think...' });

		expect(msg.thinking).toBe('Let me think...');
		expect(msg.timeline).toEqual([{ kind: 'thinking', text: 'Let me think...' }]);
	});

	it('starts a new thinking entry after a tool break', () => {
		let msg = blankAssistant();
		msg = applyChatEvent(msg, { type: 'thinking', content: 'A' });
		msg = applyChatEvent(msg, {
			type: 'tool_use',
			tool_use_id: 't1',
			name: 'web_search',
			input: { q: 'foo' },
		});
		msg = applyChatEvent(msg, { type: 'thinking', content: 'B' });

		expect(msg.timeline).toEqual([
			{ kind: 'thinking', text: 'A' },
			{ kind: 'tool', toolCallId: 't1' },
			{ kind: 'thinking', text: 'B' },
		]);
	});

	it('records tool_use as a pending call and adds it to the timeline', () => {
		const msg = applyChatEvent(blankAssistant(), {
			type: 'tool_use',
			tool_use_id: 't1',
			name: 'web_search',
			input: { q: 'foo' },
			display: { icon: '🌐', present: '🌐 Searching the web for "foo"' },
		});

		expect(msg.tool_calls).toEqual([
			{
				id: 't1',
				name: 'web_search',
				input: { q: 'foo' },
				display: { icon: '🌐', present: '🌐 Searching the web for "foo"' },
				status: 'pending',
			},
		]);
		expect(msg.timeline).toEqual([{ kind: 'tool', toolCallId: 't1' }]);
	});

	it('flips matching tool_call to completed on tool_result', () => {
		let msg = applyChatEvent(blankAssistant(), {
			type: 'tool_use',
			tool_use_id: 't1',
			name: 'web_search',
			input: {},
		});
		msg = applyChatEvent(msg, {
			type: 'tool_result',
			tool_use_id: 't1',
			content: '[]',
		});

		expect(msg.tool_calls?.[0]?.status).toBe('completed');
		expect(msg.tool_calls?.[0]?.result).toBe('[]');
	});

	it('records tool_progress without completing the tool', () => {
		let msg = blankAssistant();
		msg = applyChatEvent(msg, {
			type: 'tool_use',
			tool_use_id: 't1',
			name: 'web_search',
			input: {},
		});
		msg = applyChatEvent(msg, {
			type: 'tool_progress',
			tool_use_id: 't1',
			content: 'fetching page',
		});

		expect(msg.tool_calls?.[0]?.status).toBe('pending');
		expect(msg.tool_calls?.[0]?.result).toBe('fetching page');
	});

	it('appends artifact payloads in arrival order', () => {
		let msg = blankAssistant();
		msg = applyChatEvent(msg, {
			type: 'artifact',
			artifact: {
				id: 'art_aaa',
				title: 'First',
				tool_use_id: 't1',
				spec: {
					root: 'p',
					elements: { p: { type: 'Page', props: {}, children: [] } },
				},
			},
		});
		msg = applyChatEvent(msg, {
			type: 'artifact',
			artifact: {
				id: 'art_bbb',
				title: 'Second',
				tool_use_id: 't2',
				spec: {
					root: 'p',
					elements: { p: { type: 'Page', props: {}, children: [] } },
				},
			},
		});
		expect(msg.artifacts?.map((a) => a.id)).toEqual(['art_aaa', 'art_bbb']);
		expect(msg.artifacts?.[1]?.title).toBe('Second');
	});

	it('marks the message failed on an error event', () => {
		const msg = applyChatEvent(blankAssistant(), {
			type: 'error',
			content: 'rate limited',
		});

		expect(msg.assistant_status).toBe('failed');
		expect(msg.content).toBe('Error: rate limited');
	});
});

describe('updateLastAssistantMessage', () => {
	it('returns the same array when the last message is not an assistant turn', () => {
		const messages: Array<ChatMessage> = [{ role: 'user', content: 'hi' }];
		const next = updateLastAssistantMessage(messages, () => blankAssistant());
		expect(next).toBe(messages);
	});

	it('only updates the trailing assistant slot', () => {
		const messages: Array<ChatMessage> = [
			{ role: 'user', content: 'hi' },
			{ role: 'assistant', content: '' },
		];
		const next = updateLastAssistantMessage(messages, (msg) => ({
			...msg,
			content: 'done',
		}));

		expect(next[0]).toBe(messages[0]);
		expect(next[1]?.content).toBe('done');
	});
});
