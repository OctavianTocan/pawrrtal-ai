'use client';

/**
 * React Query hook for lazily fetching a single workspace file's text content.
 *
 * Enabled only when both `workspaceId` and `filePath` are non-null — callers
 * pass `null` for either argument to suspend fetching (e.g. when no file is
 * currently open in the document viewer).
 *
 * The content is cached by `(workspaceId, filePath)` so switching between
 * previously-opened files does not re-fetch.
 */

import { useQuery } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import type { WorkspaceFileApiResponse } from '../types';

export interface WorkspaceFileResult {
  /**
   * File content as a UTF-8 string, or `null` while loading / on error.
   * Consumers should render a loading state when `isLoading` is true and
   * `content` is null.
   */
  content: string | null;
  /** True while the file fetch is in-flight. */
  isLoading: boolean;
  /** True if the fetch failed (file not found, permission error, etc.). */
  isError: boolean;
}

/**
 * Hook: fetch one workspace file's text content.
 *
 * @param workspaceId - UUID of the workspace that owns the file.
 * @param filePath    - Workspace-relative POSIX path, e.g. `memory/note.md`.
 *                      Pass `null` when no file is open.
 */
export function useWorkspaceFile(workspaceId: string | null, filePath: string | null): WorkspaceFileResult {
  const authedFetch = useAuthedFetch();

  // Both IDs must be present; otherwise the hook is idle.
  const enabled = !!workspaceId && !!filePath;

  const query = useQuery<WorkspaceFileApiResponse>({
    queryKey: ['workspace-file', workspaceId ?? '', filePath ?? ''],
    queryFn: async () => {
      // `enabled` above guarantees both are non-null when this runs.
      const wsId = workspaceId ?? '';
      const fp = filePath ?? '';
      const res = await authedFetch(API_ENDPOINTS.workspaces.file(wsId, fp));
      return res.json() as Promise<WorkspaceFileApiResponse>;
    },
    enabled,
    // Cache file content for 60 seconds — aggressive enough to stay fresh
    // while the user edits, conservative enough to avoid staleness.
    staleTime: 60 * 1000,
  });

  return {
    content: query.data?.content ?? null,
    isLoading: enabled && query.isLoading,
    isError: query.isError,
  };
}
