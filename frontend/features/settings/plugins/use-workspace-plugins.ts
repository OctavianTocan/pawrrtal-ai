'use client';

import { type UseMutationResult, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { useAuthedQuery } from '@/hooks/use-authed-query';
import { API_ENDPOINTS } from '@/lib/api';
import { useDefaultWorkspaceId } from '../workspace-env/use-workspace-env';
import type { WorkspacePluginsResponse } from './types';

const WORKSPACE_PLUGINS_QUERY_KEY = ['workspace-plugins'] as const;

interface UpdateWorkspacePluginInput {
  pluginId: string;
  enabled: boolean;
}

export function useWorkspacePlugins(): ReturnType<typeof useAuthedQuery<WorkspacePluginsResponse>> {
  const workspaceId = useDefaultWorkspaceId();
  return useAuthedQuery<WorkspacePluginsResponse>(
    [...WORKSPACE_PLUGINS_QUERY_KEY, workspaceId ?? ''],
    workspaceId ? API_ENDPOINTS.workspaces.plugins(workspaceId) : '',
    { enabled: workspaceId !== null }
  );
}

export function useUpdateWorkspacePlugin(): UseMutationResult<
  WorkspacePluginsResponse,
  Error,
  UpdateWorkspacePluginInput
> {
  const fetcher = useAuthedFetch();
  const queryClient = useQueryClient();
  const workspaceId = useDefaultWorkspaceId();

  return useMutation({
    mutationKey: ['workspace-plugins', 'update', workspaceId ?? ''],
    mutationFn: async ({ pluginId, enabled }: UpdateWorkspacePluginInput): Promise<WorkspacePluginsResponse> => {
      if (!workspaceId) {
        throw new Error('Cannot update plugins: default workspace has not loaded yet.');
      }
      const response = await fetcher(API_ENDPOINTS.workspaces.plugin(workspaceId, pluginId), {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      return (await response.json()) as WorkspacePluginsResponse;
    },
    onSuccess: (next) => {
      queryClient.setQueryData<WorkspacePluginsResponse>([...WORKSPACE_PLUGINS_QUERY_KEY, workspaceId ?? ''], next);
    },
  });
}
