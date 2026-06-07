'use client';

import type * as React from 'react';
import { PluginsSectionView } from '../plugins/PluginsSectionView';
import type { WorkspacePlugin } from '../plugins/types';
import { useUpdateWorkspacePlugin, useWorkspacePlugins } from '../plugins/use-workspace-plugins';
import { extractApiErrorMessage } from '../workspace-env/use-workspace-env';

export function PluginsSection(): React.JSX.Element {
	const query = useWorkspacePlugins();
	const mutation = useUpdateWorkspacePlugin();

	const handleTogglePlugin = (plugin: WorkspacePlugin, enabled: boolean): void => {
		mutation.mutate({ pluginId: plugin.plugin_id, enabled });
	};

	const error = mutation.error ?? query.error;
	const errorMessage = error
		? extractApiErrorMessage(error, 'Failed to load workspace plugins.')
		: null;

	return (
		<PluginsSectionView
			errorMessage={errorMessage}
			isLoading={query.isLoading}
			onTogglePlugin={handleTogglePlugin}
			plugins={query.data?.plugins ?? []}
			updatingPluginId={mutation.isPending ? (mutation.variables?.pluginId ?? null) : null}
		/>
	);
}
