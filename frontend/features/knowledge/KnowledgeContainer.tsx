'use client';

/**
 * Container for the Knowledge surface.
 *
 * Owns:
 *  - URL state parsing (`?view=` and `?path=`) — delegated to
 *    {@link useKnowledgeUrlState}.
 *  - Live workspace data via {@link useWorkspaceTree} and
 *    {@link useWorkspaceFile} (real API, not mock) — also inside
 *    {@link useKnowledgeUrlState}.
 *  - Translation of UI events (select view, open child, close file, ...)
 *    into `router.replace` calls — delegated to
 *    {@link useKnowledgeNavigation}.
 *
 * Renders the pure {@link KnowledgeView} with everything pre-resolved.
 *
 * ──────────────────────────────────────────────────────────────────────────
 * Data flow
 * ──────────────────────────────────────────────────────────────────────────
 * 1. `useWorkspaceTree()` fetches workspace list → picks default workspace
 *    → fetches its flat file-tree → converts to recursive `FileTreeNode`.
 * 2. URL `?path=` is parsed into segments.  `findNodeByPath` walks the
 *    in-memory tree to resolve the current folder and open-file node.
 * 3. When a `.md` file is open, `useWorkspaceFile()` fetches its text
 *    content lazily (keyed by workspace + path so results are cached
 *    across navigations).
 * 4. Loading / error states are surfaced through dedicated empty-state
 *    wrappers so the rest of the view is unaffected.
 */

import { AlertCircleIcon, LoaderIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useCallback } from 'react';
import { KNOWLEDGE_VIEWS } from './constants';
import { useWriteWorkspaceFile } from './hooks/use-write-workspace-file';
import { KnowledgeView } from './KnowledgeView';
import { KNOWLEDGE_MEMORY_CARDS } from './mock-data';
import { useKnowledgeNavigation } from './use-knowledge-navigation';
import { useKnowledgeUrlState } from './use-knowledge-url-state';

// ---------------------------------------------------------------------------
// Inline loading / error states
// ---------------------------------------------------------------------------

/** Spinner shown while the workspace tree loads. */
function TreeLoadingState(): ReactNode {
  return (
    <div className="flex h-full items-center justify-center text-muted-foreground">
      <LoaderIcon aria-hidden="true" className="size-4 animate-spin" />
      <span className="ml-2 text-[13px]">Loading workspace&hellip;</span>
    </div>
  );
}

/** Error banner shown when the workspace tree fetch fails. */
function TreeErrorState({ message }: { message: string }): ReactNode {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center text-muted-foreground">
      <AlertCircleIcon aria-hidden="true" className="size-5 text-destructive" />
      <p className="font-medium text-[13px] text-foreground">Couldn't load your workspace</p>
      <p className="max-w-[340px] text-[12px]">{message}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Container
// ---------------------------------------------------------------------------

/**
 * Container component. Reads the URL, resolves it to render-ready data,
 * and forwards everything to the pure View. Always rendered as a client
 * component because the underlying hooks need `useSearchParams`.
 */
export function KnowledgeContainer(): ReactNode {
  const { activeView, folderSegments, currentNode, crumbs, openFile, tree, workspaceId, openFilePath } =
    useKnowledgeUrlState();
  const handlers = useKnowledgeNavigation(folderSegments);

  // File-write mutation. The hook is always called (Rules of Hooks); when
  // `workspaceId` is null the mutation rejects, which is surfaced as an
  // inline banner inside the DocumentViewer.
  const writeFile = useWriteWorkspaceFile(workspaceId);

  // Save handler: only constructed when there's an open file path so the
  // `Edit` button stays hidden on folder views (the viewer hides it when
  // `onSave` is undefined).
  const handleSaveFile = useCallback(
    async (newContent: string) => {
      if (!openFilePath) {
        throw new Error('No file is open — cannot save.');
      }
      await writeFile.mutateAsync({ filePath: openFilePath, content: newContent });
    },
    [openFilePath, writeFile]
  );
  const onSaveFile = openFilePath ? handleSaveFile : undefined;

  // Surface tree loading / error inline so the sub-sidebar stays
  // visible (the user can still switch to Memory / Brain Access while
  // files load).
  if (tree.isLoading && activeView === KNOWLEDGE_VIEWS.myFiles) {
    return (
      <KnowledgeView
        activeView={activeView}
        contentOverride={<TreeLoadingState />}
        crumbs={crumbs}
        currentNode={null}
        memoryCards={KNOWLEDGE_MEMORY_CARDS}
        openFile={null}
        {...handlers}
      />
    );
  }

  if (tree.isError && activeView === KNOWLEDGE_VIEWS.myFiles) {
    return (
      <KnowledgeView
        activeView={activeView}
        contentOverride={<TreeErrorState message={tree.error?.message ?? 'Unknown error — check the backend.'} />}
        crumbs={crumbs}
        currentNode={null}
        memoryCards={KNOWLEDGE_MEMORY_CARDS}
        openFile={null}
        {...handlers}
      />
    );
  }

  return (
    <KnowledgeView
      activeView={activeView}
      crumbs={crumbs}
      currentNode={currentNode}
      memoryCards={KNOWLEDGE_MEMORY_CARDS}
      onSaveFile={onSaveFile}
      openFile={openFile}
      {...handlers}
    />
  );
}
