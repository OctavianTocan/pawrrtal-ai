'use client';

/**
 * Navigation handlers for the Knowledge surface.
 *
 * Each handler turns a UI event into a `router.replace(...)` call so
 * the URL remains the source of truth.  Extracted from
 * `KnowledgeContainer` so the container body stays under the
 * `noExcessiveLinesPerFunction` budget.
 */

import { useRouter } from 'next/navigation';
import { useCallback } from 'react';
import { KNOWLEDGE_QUERY_KEYS, KNOWLEDGE_VIEWS } from './constants';
import type { KnowledgeViewProps } from './KnowledgeView';
import { joinKnowledgePath } from './path-utils';
import type { KnowledgeViewId } from './types';

/**
 * Builds a `?view=...&path=...` query string fragment.
 *
 * `path` is omitted entirely when empty — keeps the URL tidy on the
 * root `my-files` view.
 */
function buildQuery(view: KnowledgeViewId, path: string): string {
  const params = new URLSearchParams();
  params.set(KNOWLEDGE_QUERY_KEYS.view, view);
  if (path) params.set(KNOWLEDGE_QUERY_KEYS.path, path);
  return params.toString();
}

/**
 * Bag of handlers that {@link KnowledgeView} expects.
 *
 * Returned by {@link useKnowledgeNavigation}; spread directly onto
 * `<KnowledgeView />` so a new handler added to the view's prop set
 * surfaces as a TypeScript error here too.  Each handler is a stable
 * callback (`useCallback`) keyed on `folderSegments` + `router` so
 * memoized children don't re-render when unrelated state changes.
 */
export interface KnowledgeNavigationHandlers {
  /** Switch the active sub-view (`my-files` / `memory` / `brain-access`). */
  onSelectView: KnowledgeViewProps['onSelectView'];
  /** Jump to a breadcrumb segment (always within `my-files`). */
  onNavigateBreadcrumb: KnowledgeViewProps['onNavigateBreadcrumb'];
  /** Descend into a child file/folder of the current folder. */
  onOpenChild: KnowledgeViewProps['onOpenChild'];
  /** Close the currently-open `.md` file and return to its parent folder. */
  onCloseFile: KnowledgeViewProps['onCloseFile'];
  /** "New file/folder" action — currently navigates to the My Files root. */
  onNew: KnowledgeViewProps['onNew'];
  /** "Share from empty state" action — navigates to Brain Access. */
  onShareFromEmptyState: KnowledgeViewProps['onShareFromEmptyState'];
}

/**
 * Build the suite of `KnowledgeView` navigation handlers, scoped to
 * the current folder so they can compose target URLs without each
 * caller threading the segments through.
 */
export function useKnowledgeNavigation(folderSegments: string[]): KnowledgeNavigationHandlers {
  const router = useRouter();

  /**
   * Push a new URL preserving whichever path segment is appropriate
   * for the destination view — `path` only makes sense inside
   * `my-files`, so other views drop it.
   *
   * `replace` (not `push`) keeps the user's actual back-button
   * behavior intuitive — switching tabs shouldn't grow history.
   */
  const navigate = useCallback(
    (view: KnowledgeViewId, path: string) => {
      const query = buildQuery(view, path);
      router.replace(`/knowledge?${query}`);
    },
    [router]
  );

  const onSelectView = useCallback<KnowledgeViewProps['onSelectView']>(
    (view) => {
      const path = view === KNOWLEDGE_VIEWS.myFiles ? joinKnowledgePath(folderSegments) : '';
      navigate(view, path);
    },
    [folderSegments, navigate]
  );

  const onNavigateBreadcrumb = useCallback<KnowledgeViewProps['onNavigateBreadcrumb']>(
    (path) => {
      navigate(KNOWLEDGE_VIEWS.myFiles, path);
    },
    [navigate]
  );

  const onOpenChild = useCallback<KnowledgeViewProps['onOpenChild']>(
    (childName) => {
      // Both files and folders descend into the same path scheme — a
      // `.md` suffix on the trailing segment is what flips the right
      // pane into document-viewer mode (see `path-utils.isFilePath`).
      const nextPath = joinKnowledgePath([...folderSegments, childName]);
      navigate(KNOWLEDGE_VIEWS.myFiles, nextPath);
    },
    [folderSegments, navigate]
  );

  const onCloseFile = useCallback<KnowledgeViewProps['onCloseFile']>(() => {
    // Drop the trailing `.md` segment so we land back on the parent folder.
    navigate(KNOWLEDGE_VIEWS.myFiles, joinKnowledgePath(folderSegments));
  }, [folderSegments, navigate]);

  const onNew = useCallback<KnowledgeViewProps['onNew']>(() => {
    // TODO: open a "create file/folder" modal scoped to the current folder.
    // For now navigate to the root of My Files so something visibly changes.
    navigate(KNOWLEDGE_VIEWS.myFiles, '');
  }, [navigate]);

  const onShareFromEmptyState = useCallback<KnowledgeViewProps['onShareFromEmptyState']>(() => {
    navigate(KNOWLEDGE_VIEWS.brainAccess, '');
  }, [navigate]);

  return {
    onSelectView,
    onNavigateBreadcrumb,
    onOpenChild,
    onCloseFile,
    onNew,
    onShareFromEmptyState,
  };
}
