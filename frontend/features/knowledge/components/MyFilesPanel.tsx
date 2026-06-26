'use client';

/**
 * Folder/file browser for the "My Files" Knowledge sub-view.
 *
 * Layout: a breadcrumb pill row at the top (no chevrons) and a vertical
 * list of folder/file rows below. Used when the current folder is NOT a
 * leaf — i.e. it contains at least one sub-folder. Leaf folders take the
 * three-column shape and render through `KnowledgeFileListColumn`
 * + `DocumentViewer` in `KnowledgeView`.
 *
 * Selection state lives entirely inside this component because nothing
 * else cares about which rows are checked. Toggling "Select" turns the
 * trailing column into a checkbox.
 */

import { CheckSquare2Icon, FolderIcon } from 'lucide-react';
import { type ReactNode, useCallback, useState } from 'react';
import type { KnowledgeBreadcrumb } from '../path-utils';
import type { FileTreeNode } from '../types';
import { EmptyState } from './EmptyState';
import { FileRow, type FileRowAction } from './FileRow';
import { KnowledgeBreadcrumbs } from './KnowledgeBreadcrumbs';

interface MyFilesPanelProps {
  currentNode: FileTreeNode | null;
  crumbs: readonly KnowledgeBreadcrumb[];
  onNavigateBreadcrumb: (path: string) => void;
  onOpenChild: (childName: string, kind: 'file' | 'folder') => void;
}

/**
 * `currentNode` may be `null` if the URL points at a missing path — in that
 * case we show the "missing folder" empty state and let the breadcrumb
 * carry the user back up.
 */
export function MyFilesPanel({ currentNode, crumbs, onNavigateBreadcrumb, onOpenChild }: MyFilesPanelProps): ReactNode {
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedNames, setSelectedNames] = useState<readonly string[]>([]);

  const toggleSelection = useCallback((name: string) => {
    // Functional update keeps the callback stable and avoids the stale
    // closure that would arise if we read `selectedNames` from scope.
    setSelectedNames((curr) => (curr.includes(name) ? curr.filter((n) => n !== name) : [...curr, name]));
  }, []);

  const handleToggleSelect = useCallback(() => {
    setSelectionMode((mode) => {
      // Leaving select mode also clears any active selection so the
      // next time the user enters it they start from a clean slate.
      if (mode) setSelectedNames([]);
      return !mode;
    });
  }, []);

  const handleAction = useCallback((action: FileRowAction, name: string) => {
    // Mock — real implementation would mutate the tree, open a modal,
    // or call out to the backend. For now we log for traceability.
    // biome-ignore lint/suspicious/noConsole: mock surface, no backend yet
    console.info('[knowledge] file row action', { action, name });
  }, []);

  if (currentNode?.kind !== 'folder') {
    return (
      <div className="flex h-full flex-col">
        <div className="flex h-12 items-center justify-between gap-2 px-3">
          <KnowledgeBreadcrumbs crumbs={crumbs} onNavigate={onNavigateBreadcrumb} />
        </div>
        <EmptyState
          icon={FolderIcon}
          title="Folder not found"
          description="The location in this URL doesn’t exist anymore. Use the breadcrumb to head back."
        />
      </div>
    );
  }

  const children = currentNode.children;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 px-3">
        <KnowledgeBreadcrumbs crumbs={crumbs} onNavigate={onNavigateBreadcrumb} />
        <div className="flex items-center gap-2">
          {selectionMode ? (
            <span className="text-[12px] text-muted-foreground">Selected: {selectedNames.length}</span>
          ) : null}
          <button
            type="button"
            onClick={handleToggleSelect}
            className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-md px-2 text-[12px] font-medium text-muted-foreground transition-colors duration-150 ease-out hover:bg-foreground-5 hover:text-foreground"
          >
            <CheckSquare2Icon aria-hidden="true" className="size-3.5" />
            {selectionMode ? 'Cancel' : 'Select'}
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        {children.length === 0 ? (
          <EmptyState
            icon={FolderIcon}
            title="This folder is empty"
            description="Drop in a file or right-click to create a new one."
          />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {children.map((child) => (
              <li key={child.name}>
                <FileRow
                  name={child.name}
                  updatedLabel={child.updatedLabel}
                  kind={child.kind}
                  selectionMode={selectionMode}
                  isSelected={selectedNames.includes(child.name)}
                  onActivate={() => onOpenChild(child.name, child.kind)}
                  onToggleSelect={() => toggleSelection(child.name)}
                  onAction={(action) => handleAction(action, child.name)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
