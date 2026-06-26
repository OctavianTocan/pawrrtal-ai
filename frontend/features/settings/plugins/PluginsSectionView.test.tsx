import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PluginsSectionView } from './PluginsSectionView';
import type { WorkspacePlugin } from './types';

const TASKS_PLUGIN: WorkspacePlugin = {
  plugin_id: 'tasks',
  name: 'Tasks',
  description: 'Manage workspace TASKS.md entries through agent tools.',
  version: '1.0.0',
  source_type: 'bundled',
  status: 'active',
  reason: null,
  enabled: true,
  manageable: true,
  manage_reason: null,
  missing_env: [],
  fingerprint: 'abc',
  manifest_path: '/repo/backend/plugins/tasks/plugin.json',
  capabilities: [
    {
      plugin_id: 'tasks',
      capability_id: 'add_task',
      key: 'tasks/add_task',
      type: 'python_tool',
      title: 'Add Task',
      description: 'Append a new task to the workspace TASKS.md file.',
      tags: ['tasks'],
      intents: ['tasks.add'],
      slots: ['tasks'],
      state: 'enabled',
      preferred: false,
      priority: 0,
      exposure: 'direct_and_catalog',
      permissions: ['filesystem_write'],
      requires_confirmation: false,
      input_schema: {},
      examples: [],
      invokable: true,
    },
  ],
};

describe('PluginsSectionView', () => {
  it('renders plugin status and capability chips', () => {
    render(
      <PluginsSectionView
        errorMessage={null}
        isLoading={false}
        onTogglePlugin={vi.fn()}
        plugins={[TASKS_PLUGIN]}
        updatingPluginId={null}
      />
    );
    expect(screen.getByRole('heading', { name: 'Plugins' })).toBeTruthy();
    expect(screen.getByText('Tasks')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();
    expect(screen.getByText('Add Task')).toBeTruthy();
  });

  it('fires the toggle callback with the next enabled state', async () => {
    const onTogglePlugin = vi.fn();
    const user = userEvent.setup();
    render(
      <PluginsSectionView
        errorMessage={null}
        isLoading={false}
        onTogglePlugin={onTogglePlugin}
        plugins={[TASKS_PLUGIN]}
        updatingPluginId={null}
      />
    );

    await user.click(screen.getByRole('switch', { name: 'Enable Tasks' }));

    expect(onTogglePlugin).toHaveBeenCalledWith(TASKS_PLUGIN, false);
  });

  it('disables toggles for runtime-global plugins', async () => {
    const onTogglePlugin = vi.fn();
    const user = userEvent.setup();
    const reason = 'This plugin controls runtime-global channel adapters.';
    const coreChannels: WorkspacePlugin = {
      ...TASKS_PLUGIN,
      plugin_id: 'core_channels',
      name: 'Core Channels',
      manageable: false,
      manage_reason: reason,
    };
    render(
      <PluginsSectionView
        errorMessage={null}
        isLoading={false}
        onTogglePlugin={onTogglePlugin}
        plugins={[coreChannels]}
        updatingPluginId={null}
      />
    );

    const toggle = screen.getByRole('switch', { name: 'Enable Core Channels' });
    await user.click(toggle);

    expect(toggle).toHaveProperty('disabled', true);
    expect(screen.getByText(reason)).toBeTruthy();
    expect(onTogglePlugin).not.toHaveBeenCalled();
  });

  it('renders missing env and error states', () => {
    render(
      <PluginsSectionView
        errorMessage="Failed to load workspace plugins."
        isLoading={false}
        onTogglePlugin={vi.fn()}
        plugins={[
          {
            ...TASKS_PLUGIN,
            plugin_id: 'notion',
            name: 'Notion',
            status: 'misconfigured',
            enabled: true,
            missing_env: ['NOTION_API_KEY'],
          },
        ]}
        updatingPluginId={null}
      />
    );

    expect(screen.getByRole('alert').textContent).toContain('Failed to load');
    expect(screen.getByText('Needs setup')).toBeTruthy();
    expect(screen.getByText('Missing: NOTION_API_KEY')).toBeTruthy();
  });
});
