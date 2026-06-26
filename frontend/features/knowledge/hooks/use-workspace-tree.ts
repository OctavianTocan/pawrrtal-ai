'use client';

/**
 * React Query hook that fetches the current user's default workspace and
 * converts its flat file-tree API response into the recursive
 * {@link FileTreeNode} structure consumed by the Knowledge UI.
 *
 * Two dependent fetches happen in sequence:
 *   1. `GET /api/v1/workspaces`       → pick the default (or first) workspace.
 *   2. `GET /api/v1/workspaces/:id/tree` → flat node list → recursive tree.
 *
 * The hook is designed to be called once inside `KnowledgeContainer` and its
 * results passed down as props; no context or global state is needed.
 */

import { useQuery } from '@tanstack/react-query';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import { flatNodesToTree } from '../path-utils';
import type { FileTreeNode, WorkspaceRead, WorkspaceTreeApiResponse } from '../types';

export interface WorkspaceTreeResult {
  /** UUID of the active workspace, or `null` while loading. */
  workspaceId: string | null;
  /**
   * Recursive file tree rooted at "My Files".  `null` until both fetches
   * complete; components should handle this with a loading skeleton or by
   * rendering an empty root.
   */
  fileTree: FileTreeNode | null;
  /** True while either network request is in-flight. */
  isLoading: boolean;
  /** True if either request failed. */
  isError: boolean;
  /** The first error encountered (workspace list or tree), if any. */
  error: Error | null;
}

/**
 * Hook: fetch the default workspace and its file tree.
 *
 * React Query caches both responses so navigating back to the Knowledge
 * route does not re-fetch unless the cache has gone stale.
 */
export function useWorkspaceTree(): WorkspaceTreeResult {
  const authedFetch = useAuthedFetch();

  // ── Step 1: workspace list ────────────────────────────────────────────────

  const workspacesQuery = useQuery<WorkspaceRead[]>({
    queryKey: ['workspaces'],
    queryFn: async () => {
      const res = await authedFetch(API_ENDPOINTS.workspaces.list);
      return res.json() as Promise<WorkspaceRead[]>;
    },
    // Keep the list fresh for 5 minutes — it's unlikely to change mid-session.
    staleTime: 5 * 60 * 1000,
  });

  // Prefer is_default; fall back to the first workspace in the list.
  const defaultWorkspace: WorkspaceRead | null =
    workspacesQuery.data?.find((w) => w.is_default) ?? workspacesQuery.data?.[0] ?? null;

  // ── Step 2: file tree (dependent on step 1) ───────────────────────────────

  const treeQuery = useQuery<WorkspaceTreeApiResponse>({
    queryKey: ['workspace-tree', defaultWorkspace?.id ?? ''],
    queryFn: async () => {
      // `enabled` above ensures defaultWorkspace is non-null when this runs.
      const wsId = defaultWorkspace?.id ?? '';
      const res = await authedFetch(API_ENDPOINTS.workspaces.tree(wsId));
      return res.json() as Promise<WorkspaceTreeApiResponse>;
    },
    // Only run once we have a workspace ID.
    enabled: !!defaultWorkspace?.id,
    staleTime: 30 * 1000,
  });

  // ── Derived state ─────────────────────────────────────────────────────────

  const fileTree: FileTreeNode | null = treeQuery.data ? flatNodesToTree(treeQuery.data.nodes) : null;

  const isLoading =
    workspacesQuery.isLoading ||
    // Tree is "loading" only while we actually have a workspace ID to fetch.
    (!!defaultWorkspace && treeQuery.isLoading);

  const isError = workspacesQuery.isError || treeQuery.isError;

  const error: Error | null = (workspacesQuery.error as Error | null) ?? (treeQuery.error as Error | null) ?? null;

  return {
    workspaceId: defaultWorkspace?.id ?? null,
    fileTree,
    isLoading,
    isError,
    error,
  };
}
