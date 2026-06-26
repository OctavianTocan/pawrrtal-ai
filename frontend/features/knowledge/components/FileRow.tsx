'use client';

/**
 * One row in the file/folder browser.
 *
 * Combines a `DropdownContextMenu` (right-click) with a three-dot trigger
 * (`DropdownPanelMenu`) — both menus share the same item tree so the user
 * can reach the same actions either way. Selection state (the leading
 * checkbox) is driven from the container; the row never owns it.
 *
 * The row body is a `<div role="button">` rather than a real `<button>`
 * because the three-dot menu trigger is itself a `<button>` and HTML
 * forbids nested buttons.
 */

import {
  DropdownContextMenu,
  DropdownContextMenuContent,
  DropdownContextMenuTrigger,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownPanelMenu,
} from '@octavian-tocan/react-dropdown';
import {
  DownloadIcon,
  FileTextIcon,
  FolderIcon,
  MoreHorizontalIcon,
  PencilIcon,
  SendIcon,
  Share2Icon,
  Trash2Icon,
} from 'lucide-react';
import type { KeyboardEvent, MouseEvent, ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface FileRowProps {
  name: string;
  updatedLabel: string;
  kind: 'file' | 'folder';
  selectionMode: boolean;
  isSelected: boolean;
  onActivate: () => void;
  onToggleSelect: () => void;
  onAction: (action: FileRowAction) => void;
}

/** All actions emitted by the per-row context/three-dot menu. */
export type FileRowAction = 'new-file' | 'new-folder' | 'rename' | 'share' | 'download' | 'publish' | 'delete';

interface RowMenuContentProps {
  onAction: (action: FileRowAction) => void;
}

/**
 * Shared menu body rendered inside both the right-click context menu and
 * the three-dot dropdown — single source of truth for the action list so
 * both surfaces stay in sync if the items ever change.
 */
function RowMenuContent({ onAction }: RowMenuContentProps): ReactNode {
  return (
    <>
      <DropdownMenuItem onSelect={() => onAction('new-file')}>
        <FileTextIcon className="size-3.5" />
        New File
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onAction('new-folder')}>
        <FolderIcon className="size-3.5" />
        New Folder
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={() => onAction('rename')}>
        <PencilIcon className="size-3.5" />
        Rename
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onAction('share')}>
        <Share2Icon className="size-3.5" />
        Share
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onAction('download')}>
        <DownloadIcon className="size-3.5" />
        Download
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onAction('publish')}>
        <SendIcon className="size-3.5" />
        Publish
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        onSelect={() => onAction('delete')}
        className="text-destructive-text data-[highlighted=true]:bg-destructive/10"
      >
        <Trash2Icon className="size-3.5" />
        Delete
      </DropdownMenuItem>
    </>
  );
}

/**
 * Single row in the My Files browser.
 *
 * Click anywhere on the row body to activate (open folder / open file),
 * unless multi-select mode is active in which case the entire row toggles
 * selection. The trailing three-dot button is always available; right-click
 * works whether or not the cursor is over the menu trigger.
 */
export function FileRow({
  name,
  updatedLabel,
  kind,
  selectionMode,
  isSelected,
  onActivate,
  onToggleSelect,
  onAction,
}: FileRowProps): ReactNode {
  const Icon = kind === 'folder' ? FolderIcon : FileTextIcon;

  const handleActivate = (): void => {
    if (selectionMode) {
      onToggleSelect();
      return;
    }
    onActivate();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    // Replicate the native `<button>` keyboard contract for the div role.
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleActivate();
    }
  };

  // Prevent clicks on the three-dot button from bubbling to the row's
  // activate handler — otherwise opening the menu would also navigate.
  const stopMouse = (event: MouseEvent<HTMLElement>): void => {
    event.stopPropagation();
  };

  return (
    <DropdownContextMenu>
      <DropdownContextMenuTrigger asChild>
        {/* biome-ignore lint/a11y/useSemanticElements: row hosts a nested three-dot <button> menu trigger; using <button> here would be invalid HTML (button-in-button). The role/tabIndex/keydown trio replicates the native button contract. */}
        <div
          role="button"
          tabIndex={0}
          onClick={handleActivate}
          onKeyDown={handleKeyDown}
          className={cn(
            'group flex h-10 w-full cursor-pointer items-center gap-2 rounded-md px-2 text-left transition-colors duration-150 ease-out',
            'focus:outline-none focus-visible:ring-1 focus-visible:ring-ring',
            isSelected ? 'bg-foreground-5' : 'hover:bg-foreground-5'
          )}
        >
          {selectionMode ? (
            <span
              aria-hidden="true"
              className={cn(
                'flex size-4 shrink-0 items-center justify-center rounded-[4px] border transition-colors duration-150',
                isSelected ? 'border-accent bg-accent text-background' : 'border-foreground/20 bg-background'
              )}
            >
              {isSelected ? <span className="text-[10px] leading-none">✓</span> : null}
            </span>
          ) : null}
          <Icon
            aria-hidden="true"
            className={cn('size-4 shrink-0', kind === 'folder' ? 'text-foreground' : 'text-muted-foreground')}
          />
          <span className="flex-1 truncate text-[13px] font-medium text-foreground">{name}</span>
          <span className="text-[12px] text-muted-foreground">{updatedLabel}</span>
          <DropdownPanelMenu
            asChild
            usePortal
            align="end"
            contentClassName="popover-styled p-1 min-w-44"
            trigger={
              <button
                type="button"
                aria-label={`More actions for ${name}`}
                onClick={stopMouse}
                className="flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity duration-150 ease-out group-hover:opacity-100 group-focus-within:opacity-100 hover:bg-foreground-5 hover:text-foreground"
              >
                <MoreHorizontalIcon aria-hidden="true" className="size-4" />
              </button>
            }
          >
            <RowMenuContent onAction={onAction} />
          </DropdownPanelMenu>
        </div>
      </DropdownContextMenuTrigger>
      <DropdownContextMenuContent>
        <RowMenuContent onAction={onAction} />
      </DropdownContextMenuContent>
    </DropdownContextMenu>
  );
}
