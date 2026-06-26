'use client';

/**
 * URL-derived state for the Knowledge surface.
 *
 * Parses `?view=` and `?path=` from the address bar, resolves them
 * against the live workspace tree (`useWorkspaceTree`), and lazily
 * fetches the open file body (`useWorkspaceFile`).  Centralising this
 * lets the container component focus on render orchestration and
 * keeps the hook surface independently testable.
 */

import { useSearchParams } from 'next/navigation';
import { useMemo } from 'react';
import { DEFAULT_KNOWLEDGE_VIEW, KNOWLEDGE_QUERY_KEYS, KNOWLEDGE_VIEWS } from './constants';
import { useWorkspaceFile } from './hooks/use-workspace-file';
import { useWorkspaceTree } from './hooks/use-workspace-tree';
import { buildBreadcrumbs, findNodeByPath, isFilePath, joinKnowledgePath, parseKnowledgePath } from './path-utils';
import type { FileTreeNode, KnowledgeViewId } from './types';

/**
 * Type guard for `?view=` values. Anything unrecognised falls back to the
 * default sub-view rather than rendering an unknown surface.
 */
function isKnowledgeViewId(value: string | null): value is KnowledgeViewId {
  if (!value) return false;
  const allowed: readonly string[] = Object.values(KNOWLEDGE_VIEWS);
  return allowed.includes(value);
}

/**
 * Empty root used as a fallback while the real workspace tree is loading.
 * Prevents downstream consumers from receiving `null` while we wait.
 */
const EMPTY_FILE_TREE: FileTreeNode = {
  kind: 'folder',
  name: 'My Files',
  updatedLabel: '',
  children: [],
};

export interface KnowledgeUrlState {
  activeView: KnowledgeViewId;
  segments: string[];
  folderSegments: string[];
  currentNode: FileTreeNode | null;
  openFileNode: FileTreeNode | null;
  crumbs: ReturnType<typeof buildBreadcrumbs>;
  openFile: { name: string; markdown: string } | null;
  tree: { isLoading: boolean; isError: boolean; error: Error | null };
  /** Workspace UUID for the active workspace; `null` while it's loading. */
  workspaceId: string | null;
  /** Workspace-relative path of the currently-open file, or `null`. */
  openFilePath: string | null;
}

/**
 * Resolve the URL + workspace data into render-ready Knowledge state.
 */
export function useKnowledgeUrlState(): KnowledgeUrlState {
  const searchParams = useSearchParams();

  const rawView = searchParams.get(KNOWLEDGE_QUERY_KEYS.view);
  const activeView: KnowledgeViewId = isKnowledgeViewId(rawView) ? rawView : DEFAULT_KNOWLEDGE_VIEW;

  const rawPath = searchParams.get(KNOWLEDGE_QUERY_KEYS.path);
  // `parseKnowledgePath` returns a fresh array on every call.
  // Memoizing on `rawPath` (a primitive string) gives downstream
  // consumers — the `useCallback` deps in `useKnowledgeNavigation`,
  // the `useMemo` deps of derived state below, the `KnowledgeView`
  // render shape — a stable reference so they don't recompute on every
  // parent render even when the URL hasn't changed.
  const segments = useMemo(() => parseKnowledgePath(rawPath), [rawPath]);

  const { workspaceId, fileTree, isLoading: treeLoading, isError: treeError, error } = useWorkspaceTree();

  const resolvedTree = fileTree ?? EMPTY_FILE_TREE;

  // `openFilePath` is a primitive string; React Query (inside
  // `useWorkspaceFile`) compares query keys by value, so memoizing
  // here would only add allocations.  Computed inline.
  const openFilePath = isFilePath(segments) ? joinKnowledgePath(segments) : null;

  const { content: fileContent, isLoading: fileLoading } = useWorkspaceFile(workspaceId, openFilePath);

  // Memoized: `Array.prototype.slice` allocates a new array each
  // call, and `folderSegments` is consumed as a `useCallback` dep in
  // `useKnowledgeNavigation`.  Without the memo, every parent render
  // would invalidate every navigation handler.
  const folderSegments = useMemo(() => (isFilePath(segments) ? segments.slice(0, -1) : segments), [segments]);

  // Memoized: `findNodeByPath` walks the tree to return a node
  // reference; without the memo we'd re-walk every parent render
  // and hand `KnowledgeView` a different reference each time even
  // when neither the tree nor the path changed.
  const currentNode = useMemo(() => findNodeByPath(resolvedTree, folderSegments), [resolvedTree, folderSegments]);

  // Same rationale as `currentNode` — a tree walk that should
  // produce a stable reference per (tree, segments) pair.
  const openFileNode = useMemo(() => {
    if (!isFilePath(segments)) return null;
    const node = findNodeByPath(resolvedTree, segments);
    if (node && node.kind === 'file') return node;
    return null;
  }, [resolvedTree, segments]);

  // Memoized: returns a fresh array; consumers (KnowledgeView
  // render + breadcrumb keys) benefit from a stable reference.
  const crumbs = useMemo(
    () => buildBreadcrumbs(resolvedTree.name, folderSegments),
    [resolvedTree.name, folderSegments]
  );

  // Build the `openFile` prop. Content is fetched lazily — while it
  // loads we pass an empty string so the DocumentViewer chrome is
  // visible immediately and the body area fills in once the fetch
  // resolves.
  const openFile =
    openFileNode !== null
      ? {
          name: openFileNode.name,
          markdown: fileLoading ? '' : (fileContent ?? ''),
        }
      : null;

  return {
    activeView,
    segments,
    folderSegments,
    currentNode,
    openFileNode,
    crumbs,
    openFile,
    tree: { isLoading: treeLoading, isError: treeError, error },
    workspaceId,
    openFilePath,
  };
}
