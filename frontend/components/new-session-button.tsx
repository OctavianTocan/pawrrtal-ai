'use client';

import {
  DropdownContextMenu,
  DropdownContextMenuContent,
  DropdownContextMenuTrigger,
  DropdownMenuItem,
} from '@octavian-tocan/react-dropdown';
import { AppWindow } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type * as React from 'react';
import { useCallback } from 'react';
import { SquarePenRounded } from '@/components/icons/SquarePenRounded';
import { Button } from '@/components/ui/button';
import { useSidebar } from '@/components/ui/sidebar';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

/** Where the new-session control is mounted — drives width and label visibility. */
export type NewSessionButtonLayout = 'sidebar' | 'headerCompact';

/** Props for {@link NewSessionButton}. */
export type NewSessionButtonProps = {
  /**
   * `sidebar` — full-width row with label (sidebar header).
   * `headerCompact` — icon-only control for the top bar when the sidebar is collapsed.
   */
  layout?: NewSessionButtonLayout;
};

/**
 * "New Session" header button with context menu and tooltip.
 *
 * Uses theme `rounded-soft` (8px) — rounder than form `rounded-control` (6px),
 * tighter than card `rounded-surface-lg` (14px).
 *
 * Left-click navigates to the root page (creating a fresh conversation).
 * Right-click opens a context menu with an "Open in New Window" option.
 * Hover shows a ⌘N keyboard shortcut hint via tooltip.
 *
 * Extracted as a standalone component for reusability — the same
 * button pattern can appear in the sidebar header, command palette, etc.
 */
export function NewSessionButton({ layout = 'sidebar' }: NewSessionButtonProps): React.JSX.Element {
  const { push } = useRouter();
  const { isMobile, setOpenMobile } = useSidebar();

  const handleNewConversation = useCallback((): void => {
    if (isMobile) {
      setOpenMobile(false);
    }
    push('/');
  }, [isMobile, push, setOpenMobile]);

  const handleOpenNewWindow = useCallback((): void => {
    if (typeof window !== 'undefined') {
      window.open('/', '_blank', 'noopener,noreferrer');
    }
  }, []);

  const isHeaderCompact = layout === 'headerCompact';

  return (
    <Tooltip>
      <DropdownContextMenu>
        <TooltipTrigger asChild>
          <DropdownContextMenuTrigger asChild>
            <Button
              aria-label="New Session"
              className={
                isHeaderCompact
                  ? 'size-7 shrink-0 cursor-pointer rounded-[7px] border border-foreground/10 bg-foreground/[0.03] text-muted-foreground shadow-none hover:bg-foreground/[0.06] hover:text-foreground'
                  : 'w-full cursor-pointer justify-start gap-2 rounded-soft bg-background px-2 py-[7px] font-normal text-[13px] shadow-minimal'
              }
              onClick={handleNewConversation}
              type="button"
              variant="ghost"
            >
              <SquarePenRounded className={isHeaderCompact ? 'size-3.5 shrink-0' : 'size-3.5 shrink-0'} />
              {isHeaderCompact ? null : 'New Session'}
            </Button>
          </DropdownContextMenuTrigger>
        </TooltipTrigger>
        <DropdownContextMenuContent>
          <DropdownMenuItem onSelect={handleOpenNewWindow}>
            <AppWindow className="size-3.5" />
            <span className="flex-1">Open in New Window</span>
          </DropdownMenuItem>
        </DropdownContextMenuContent>
      </DropdownContextMenu>
      <TooltipContent side={isHeaderCompact ? 'bottom' : 'right'}>⌘N</TooltipContent>
    </Tooltip>
  );
}
