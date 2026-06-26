'use client';

import type * as React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

/** Row in the shortcuts reference dialog. */
type ShortcutRow = {
  /** Stable key and human-readable action name. */
  id: string;
  /** Primary description shown on the left. */
  action: string;
  /** macOS / iOS style shortcut label. */
  keysMac: string;
  /** Windows / Linux style shortcut label. */
  keysWin: string;
};

const SHORTCUT_ROWS: readonly ShortcutRow[] = [
  {
    id: 'sidebar',
    action: 'Toggle sidebar',
    keysMac: '⌘B',
    keysWin: 'Ctrl+B',
  },
  {
    id: 'new-session',
    action: 'New session',
    keysMac: '⌘N',
    keysWin: 'Ctrl+N',
  },
  {
    id: 'plan-strip',
    action: 'Show or hide plan strip in the composer',
    keysMac: '⇧Tab',
    keysWin: 'Shift+Tab',
  },
] as const;

/** Props for {@link KeyboardShortcutsDialog}. */
export type KeyboardShortcutsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When true, show ⌘/⇧ style labels; otherwise Ctrl/Shift. */
  isMac: boolean;
};

/**
 * Modal listing global shortcuts implemented in the desktop shell layout.
 *
 * Opened from the header help menu; keeps copy aligned with actual handlers
 * (see `SidebarProvider` for ⌘B / Ctrl+B, `NewSessionButton` tooltip for ⌘N).
 */
export function KeyboardShortcutsDialog({
  open,
  onOpenChange,
  isMac,
}: KeyboardShortcutsDialogProps): React.JSX.Element {
  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-h-[min(32rem,90vh)] gap-4 overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-foreground">Keyboard shortcuts</DialogTitle>
        </DialogHeader>
        <ul className="flex flex-col gap-1.5">
          {SHORTCUT_ROWS.map((row) => (
            <li
              className="flex items-center justify-between gap-4 border-foreground/10 border-b py-2.5 text-sm last:border-b-0"
              key={row.id}
            >
              <span className="min-w-0 text-pretty text-foreground">{row.action}</span>
              <kbd
                className={cn(
                  'shrink-0 rounded-control border border-border/60 bg-foreground/[0.04] px-2 py-1 font-mono text-[11px] text-foreground tabular-nums tracking-wide'
                )}
              >
                {isMac ? row.keysMac : row.keysWin}
              </kbd>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
