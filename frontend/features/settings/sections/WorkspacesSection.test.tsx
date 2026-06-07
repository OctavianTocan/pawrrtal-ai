import { describe, expect, it } from 'vitest';
import type { WorkspaceEnvResponse } from '../workspace-env/use-workspace-env';
import { workspaceEnvKeyMetasForResponse } from './WorkspacesSection';

describe('workspaceEnvKeyMetasForResponse', () => {
	it('includes plugin-declared env metadata after built-in keys', () => {
		const response: WorkspaceEnvResponse = {
			vars: {
				GEMINI_API_KEY: '',
				CUSTOM_PLUGIN_TOKEN: '',
			},
			keys: [
				{
					key: 'GEMINI_API_KEY',
					label: 'Generic Gemini Label',
					description: 'Generic backend metadata.',
					secret: true,
					required: false,
					source: 'kernel',
					help_url: null,
				},
				{
					key: 'CUSTOM_PLUGIN_TOKEN',
					label: 'Custom Plugin Token',
					description: 'Token configured per workspace for this plugin.',
					secret: true,
					required: true,
					source: 'plugin',
					help_url: 'https://example.com/plugin-token',
				},
			],
		};

		const metas = workspaceEnvKeyMetasForResponse(response);

		expect(metas[0]?.key).toBe('GEMINI_API_KEY');
		expect(metas.find((meta) => meta.key === 'GEMINI_API_KEY')?.label).toBe('Gemini API Key');
		expect(metas.find((meta) => meta.key === 'CUSTOM_PLUGIN_TOKEN')).toMatchObject({
			label: 'Custom Plugin Token',
			description: 'Token configured per workspace for this plugin.',
			placeholder: 'Your Custom Plugin Token',
			url: 'https://example.com/plugin-token',
		});
	});
});
