/**
 * Top-bar chrome for the app shell.
 *
 * Split out of `AppShell.tsx` to keep that file under the 500-LOC budget.
 * Owns the workspace selector, help menu, history controls, and the
 * outer header strip that composes them. `AppShell` is the only consumer.
 *
 * @fileoverview Header strip rendered above the sidebar + content.
 */

'use client';

import { DropdownMenuItem, DropdownMenuSeparator, DropdownPanelMenu } from '@octavian-tocan/react-dropdown';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BookOpenIcon,
  CheckIcon,
  ChevronDownIcon,
  CircleHelpIcon,
  DatabaseIcon,
  ExternalLinkIcon,
  FolderPlusIcon,
  MessageSquareIcon,
  SettingsIcon,
  ShieldCheckIcon,
  WorkflowIcon,
  ZapIcon,
} from 'lucide-react';
import React from 'react';
import { KeyboardShortcutsDialog } from '@/components/keyboard-shortcuts-dialog';
import { NewSessionButton } from '@/components/new-session-button';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { SidebarTrigger, useSidebar } from '@/components/ui/sidebar';
import { OPEN_ONBOARDING_EVENT } from '@/features/onboarding/OnboardingModal';
import { useIsMacDesktop } from '@/hooks/use-is-mac-desktop';
import { cn } from '@/lib/utils';

const HELP_LINKS = [
  { label: 'Sources', icon: DatabaseIcon },
  { label: 'Skills', icon: ZapIcon },
  { label: 'Statuses', icon: CheckIcon },
  { label: 'Permissions', icon: ShieldCheckIcon },
  { label: 'Automations', icon: WorkflowIcon },
  { label: 'Messaging', icon: MessageSquareIcon },
] as const;

/**
 * Fired by the workspace dropdown's "Add Workspace..." item. Opens the
 * three-step **workspace** onboarding modal (Welcome → Create workspace →
 * Local workspace) — NOT the home-page personalization wizard. The two
 * are distinct surfaces: workspace lives behind this dropdown, while
 * personalization fires on every fresh page load.
 */
function handleOpenOnboarding(): void {
  window.dispatchEvent(new Event(OPEN_ONBOARDING_EVENT));
}

/**
 * Back / Forward buttons that drive the browser history stack so the user can
 * step between previously-visited routes (chat → settings → another chat,
 * etc.). Wired through `window.history` directly because Next.js's
 * `router.back()` lacks a corresponding `forward()` and we want both
 * directions to behave identically.
 */
function AppHistoryControls(): React.JSX.Element {
  const handleBack = React.useCallback(() => {
    if (typeof window !== 'undefined') {
      window.history.back();
    }
  }, []);

  const handleForward = React.useCallback(() => {
    if (typeof window !== 'undefined') {
      window.history.forward();
    }
  }, []);

  return (
    <div className="flex items-center gap-0.5">
      <Button
        aria-label="Back"
        className="size-7 cursor-pointer rounded-[7px] text-muted-foreground transition-[background-color,color] duration-150 hover:bg-foreground/[0.055] hover:text-foreground"
        onClick={handleBack}
        size="icon-xs"
        title="Back"
        type="button"
        variant="ghost"
      >
        <ArrowLeftIcon aria-hidden="true" className="size-4" />
      </Button>
      <Button
        aria-label="Forward"
        className="size-7 cursor-pointer rounded-[7px] text-muted-foreground transition-[background-color,color] duration-150 hover:bg-foreground/[0.055] hover:text-foreground"
        onClick={handleForward}
        size="icon-xs"
        title="Forward"
        type="button"
        variant="ghost"
      >
        <ArrowRightIcon aria-hidden="true" className="size-4" />
      </Button>
    </div>
  );
}

function WorkspaceSelector(): React.JSX.Element {
  return (
    <DropdownPanelMenu
      asChild
      usePortal
      align="start"
      contentClassName="popover-styled p-1 min-w-56"
      trigger={
        <Button
          aria-label="Select workspace"
          className="h-7 gap-2 rounded-[7px] border border-foreground/10 bg-foreground/[0.03] px-2.5 text-[13px] font-normal text-foreground hover:bg-foreground/[0.06] aria-expanded:bg-foreground/[0.06]"
          type="button"
          variant="ghost"
        >
          <span className="flex size-4.5 items-center justify-center rounded-full bg-foreground/10 text-[10px] font-medium">
            A
          </span>
          <span>Pawrrtal</span>
          <ChevronDownIcon aria-hidden="true" className="size-3.5 text-muted-foreground" />
        </Button>
      }
    >
      <DropdownMenuItem className="justify-between">
        <span className="flex items-center gap-2">
          <span className="flex size-5 items-center justify-center rounded-full bg-foreground/10 text-[11px] font-medium">
            A
          </span>
          Pawrrtal
        </span>
        <CheckIcon aria-hidden="true" className="size-3.5 text-foreground" />
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onSelect={handleOpenOnboarding}>
        <FolderPlusIcon aria-hidden="true" className="size-3.5" />
        Add Workspace&hellip;
      </DropdownMenuItem>
    </DropdownPanelMenu>
  );
}

function HelpMenu(): React.JSX.Element {
  const [shortcutsOpen, setShortcutsOpen] = React.useState(false);
  const [isAppleLike] = React.useState(
    () => typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent)
  );

  return (
    <>
      <KeyboardShortcutsDialog isMac={isAppleLike} onOpenChange={setShortcutsOpen} open={shortcutsOpen} />
      <DropdownPanelMenu
        asChild
        usePortal
        align="end"
        contentClassName="popover-styled p-1 min-w-56"
        trigger={
          <Button
            aria-label="Open documentation menu"
            className="size-7 rounded-[7px] text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground aria-expanded:bg-foreground/[0.05]"
            size="icon-xs"
            type="button"
            variant="ghost"
          >
            <CircleHelpIcon aria-hidden="true" className="size-4" />
          </Button>
        }
      >
        {HELP_LINKS.map((link) => {
          const Icon = link.icon;

          return (
            <DropdownMenuItem className="justify-between" key={link.label}>
              <span className="flex items-center gap-2">
                <Icon aria-hidden="true" className="size-3.5" />
                {link.label}
              </span>
              <ExternalLinkIcon aria-hidden="true" className="size-3.5 text-muted-foreground" />
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem>
          <BookOpenIcon aria-hidden="true" className="size-3.5" />
          All Documentation
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            setShortcutsOpen(true);
          }}
        >
          <SettingsIcon aria-hidden="true" className="size-3.5" />
          Keyboard Shortcuts
        </DropdownMenuItem>
      </DropdownPanelMenu>
    </>
  );
}

/**
 * Top-bar chrome rendered as a full-width overlay above the sidebar and
 * content. Lives outside the sidebar so its controls (sidebar trigger,
 * history, workspace selector) stay in their original screen positions
 * even when the sidebar is hidden — the sidebar visually extends
 * underneath this header.
 *
 * macOS Electron uses the **native title bar** (`titleBarStyle: 'default'`
 * in `electron/src/window-chrome.ts`): full-size traffic lights live in
 * the system strip above the web view, so this row does not need extra
 * left inset. If you switch to `hidden` / `hiddenInset`, pad this header
 * in the layout yourself.
 */
export function AppShellHeader(): React.JSX.Element {
  const isMacDesktop = useIsMacDesktop();
  const { isMobile, state } = useSidebar();
  const showHeaderNewSession = !isMobile && state === 'collapsed';

  return (
    <header
      className={cn(
        'absolute inset-x-0 top-0 z-20 flex h-10 shrink-0 items-center border-0 py-0 pr-3 pl-3 outline-none focus:outline-none focus-visible:outline-none',
        // On macOS Electron the custom header remains a drag surface for
        // window moves (native bar is also draggable).
        isMacDesktop && '[-webkit-app-region:drag]'
      )}
    >
      {/* Left control cluster — `no-drag` so clicks land on the
			    individual buttons instead of being intercepted as window
			    drags. Sized to its content (no `flex-1`) so the middle
			    space is left as a draggable gutter. */}
      <div className={cn('flex items-center gap-2', isMacDesktop && '[-webkit-app-region:no-drag]')}>
        <SidebarTrigger className="size-7 cursor-pointer" />
        <AppHistoryControls />
        <Separator orientation="vertical" className="ml-1 data-vertical:h-4 data-vertical:self-auto" />
        <WorkspaceSelector />
        {showHeaderNewSession ? <NewSessionButton layout="headerCompact" /> : null}
      </div>

      {/* Spacer that consumes the leftover width and stays inside
			    the header's drag region — this is the user-facing handle
			    they can grab to move the window. */}
      <div className="min-w-0 flex-1" />

      {/* Right control cluster — also `no-drag` so the +/help
			    buttons keep working. */}
      <div className={cn('flex items-center gap-1', isMacDesktop && '[-webkit-app-region:no-drag]')}>
        <HelpMenu />
      </div>
    </header>
  );
}
