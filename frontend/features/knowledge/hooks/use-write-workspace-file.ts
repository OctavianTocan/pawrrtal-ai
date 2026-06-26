'use client';

/**
 * React Query mutation hook for writing (creating or replacing) a single
 * workspace file.
 *
 * On success the hook automatically invalidates the `workspace-file` query
 * for the saved path so the DocumentViewer's cached content stays in sync
 * with what we just wrote.
 *
 * Usage:
 * ```ts
 * const { mutate, isPending } = useWriteWorkspaceFile(workspaceId);
 * mutate({ filePath: 'notes/readme.md', content: newMarkdown });
 * ```
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import type { WorkspaceFileApiResponse } from '../types';

interface WriteFileArgs {
  /** Workspace-relative POSIX path, e.g. `memory/note.md`. */
  filePath: string;
  /** Full UTF-8 text content to write. */
  content: string;
}

/**
 * Hook: write a workspace file via PUT and refresh the cached read query.
 *
 * @param workspaceId - UUID of the workspace that owns the file.  Pass
 *   `null` to obtain a hook that always returns an error on mutation
 *   (safe to call before the workspace loads).
 */
export function useWriteWorkspaceFile(workspaceId: string | null) {
  const authedFetch = useAuthedFetch();
  const queryClient = useQueryClient();

  return useMutation<WorkspaceFileApiResponse, Error, WriteFileArgs>({
    mutationFn: async ({ filePath, content }) => {
      if (!workspaceId) {
        throw new Error('No workspace selected — cannot save file.');
      }
      const res = await authedFetch(API_ENDPOINTS.workspaces.writeFile(workspaceId, filePath), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}: Failed to save file`);
      }
      return res.json() as Promise<WorkspaceFileApiResponse>;
    },

    onSuccess: (_data, { filePath }) => {
      // Invalidate the matching read query so any subsequent open of this
      // file re-fetches the latest content from the server.
      queryClient.invalidateQueries({
        queryKey: ['workspace-file', workspaceId ?? '', filePath],
      });
    },
  });
}
