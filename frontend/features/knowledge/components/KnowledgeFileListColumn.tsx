'use client';

/**
 * Middle column rendered when the user is inside a leaf folder.
 *
 * Layout: breadcrumb pills at the top, then a vertical list of file rows
 * scoped to a single folder. Each row has a circular icon, a bold filename,
 * and a "Today"-style timestamp on a second line. The active row (the one
 * matching the currently-open document) gets a pill background.
 *
 * Pure presentation — selection state belongs to the URL, not this
 * component, so a fresh `activeFileName` prop drives the highlight.
 */

import { FileTextIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { KnowledgeBreadcrumb } from '../path-utils';
import type { FileTreeNode } from '../types';
import { KnowledgeBreadcrumbs } from './KnowledgeBreadcrumbs';

interface KnowledgeFileListColumnProps {
  /** Breadcrumb pills shown at the top of the column. */
  crumbs: readonly KnowledgeBreadcrumb[];
  /** Fired when a breadcrumb pill is clicked. */
  onNavigateBreadcrumb: (path: string) => void;
  /** Files to render. Caller is responsible for filtering out folders. */
  files: readonly FileTreeNode[];
  /** Filename of the currently-open document, or `null` if no doc is open. */
  activeFileName: string | null;
  /** Fired when a file row is activated. */
  onOpenFile: (filename: string) => void;
}

/**
 * Pure presentation. Folders are intentionally not handled here — by
 * the time we render this column the parent has already verified the
 * folder is a leaf (no sub-folders), so any folder child is a programming
 * error and renders the file icon as a defensive fallback.
 */
export function KnowledgeFileListColumn({
  crumbs,
  onNavigateBreadcrumb,
  files,
  activeFileName,
  onOpenFile,
}: KnowledgeFileListColumnProps): ReactNode {
  return (
    <div className="flex min-h-0 w-[280px] shrink-0 flex-col">
      <div className="flex h-12 shrink-0 items-center px-3">
        <KnowledgeBreadcrumbs crumbs={crumbs} onNavigate={onNavigateBreadcrumb} />
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {files.map((file) => {
          const isActive = file.name === activeFileName;
          return (
            <li key={file.name}>
              <button
                type="button"
                onClick={() => onOpenFile(file.name)}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'flex w-full cursor-pointer items-center gap-2.5 rounded-md p-2 text-left transition-colors duration-150 ease-out',
                  isActive ? 'bg-foreground-5 text-foreground' : 'text-foreground hover:bg-foreground-5'
                )}
              >
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full',
                    isActive ? 'bg-background text-foreground' : 'bg-foreground-5 text-muted-foreground'
                  )}
                >
                  <FileTextIcon aria-hidden="true" className="size-3.5" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-medium leading-tight">{file.name}</span>
                  <span className="text-[11px] text-muted-foreground">{file.updatedLabel}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
