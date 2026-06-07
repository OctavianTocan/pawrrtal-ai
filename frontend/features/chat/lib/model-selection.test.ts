import { describe, expect, it } from 'vitest';
import type { ChatModelOption } from '../hooks/use-chat-models';
import { resolveSelectedModelId } from './model-selection';

const DEFAULT_MODEL: ChatModelOption = {
	id: 'google-ai:google/gemini-3-flash-preview',
	host: 'google-ai',
	vendor: 'google',
	model: 'gemini-3-flash-preview',
	display_name: 'Gemini 3 Flash Preview',
	short_name: 'Gemini 3 Flash',
	description: 'Default fixture model',
};

const MODELS: ChatModelOption[] = [
	DEFAULT_MODEL,
	{
		id: 'openai-codex:openai/gpt-5.5',
		host: 'openai-codex',
		vendor: 'openai',
		model: 'gpt-5.5',
		display_name: 'GPT-5.5',
		short_name: 'GPT-5.5',
		description: 'Stored conversation model',
	},
	{
		id: 'xai:xai/grok-4.3',
		host: 'xai',
		vendor: 'xai',
		model: 'grok-4.3',
		display_name: 'Grok 4.3',
		short_name: 'Grok 4.3',
		description: 'In-session choice model',
	},
];

describe('resolveSelectedModelId', () => {
	it('uses the stored conversation model before the catalog default', () => {
		expect(
			resolveSelectedModelId({
				userChoice: null,
				initialModelId: 'openai-codex:openai/gpt-5.5',
				models: MODELS,
				defaultEntry: DEFAULT_MODEL,
			})
		).toBe('openai-codex:openai/gpt-5.5');
	});

	it('keeps an explicit in-session choice above the stored conversation model', () => {
		expect(
			resolveSelectedModelId({
				userChoice: 'xai:xai/grok-4.3',
				initialModelId: 'openai-codex:openai/gpt-5.5',
				models: MODELS,
				defaultEntry: DEFAULT_MODEL,
			})
		).toBe('xai:xai/grok-4.3');
	});

	it('falls back to the catalog default when stored and selected models are stale', () => {
		expect(
			resolveSelectedModelId({
				userChoice: 'missing:vendor/model',
				initialModelId: 'also-missing:vendor/model',
				models: MODELS,
				defaultEntry: DEFAULT_MODEL,
			})
		).toBe('google-ai:google/gemini-3-flash-preview');
	});
});
