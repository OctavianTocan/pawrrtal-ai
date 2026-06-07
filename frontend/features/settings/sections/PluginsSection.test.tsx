import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PluginsSection } from './PluginsSection';

const { mutate, useUpdateWorkspacePlugin, useWorkspacePlugins } = vi.hoisted(() => ({
	mutate: vi.fn(),
	useUpdateWorkspacePlugin: vi.fn(),
	useWorkspacePlugins: vi.fn(),
}));

vi.mock('../plugins/use-workspace-plugins', () => ({
	useUpdateWorkspacePlugin,
	useWorkspacePlugins,
}));

describe('PluginsSection', () => {
	it('passes plugin toggle mutations through to the workspace plugin hook', async () => {
		const user = userEvent.setup();
		useWorkspacePlugins.mockReturnValue({
			data: {
				workspace_id: 'workspace-1',
				fingerprint: 'fp',
				plugins: [
					{
						plugin_id: 'python_shell',
						name: 'Python Shell',
						description: 'Expose the trusted in-process Python execution tool.',
						version: '1.0.0',
						source_type: 'bundled',
						status: 'disabled',
						reason: 'Plugin disabled.',
						enabled: false,
						missing_env: [],
						fingerprint: 'abc',
						manifest_path: '/repo/backend/plugins/python_shell/plugin.json',
						capabilities: [],
					},
				],
			},
			error: null,
			isLoading: false,
		});
		useUpdateWorkspacePlugin.mockReturnValue({
			error: null,
			isPending: false,
			mutate,
			variables: undefined,
		});

		render(<PluginsSection />);
		await user.click(screen.getByRole('switch', { name: 'Enable Python Shell' }));

		expect(mutate).toHaveBeenCalledWith({ pluginId: 'python_shell', enabled: true });
	});
});
