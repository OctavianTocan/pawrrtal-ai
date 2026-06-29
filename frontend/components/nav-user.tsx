/**
 * Sidebar footer user menu — avatar trigger + Claude-style account dropdown.
 *
 * Mirrors the Claude.ai sidebar pattern: a low-profile profile row anchored at
 * the bottom of the sidebar that opens a dropdown above it, with sections for
 * account preferences (Settings, Language, Help), product surfaces (plans,
 * apps, gift, learn more), and a sign-out action.
 *
 * @fileoverview Profile button + dropdown rendered as the SidebarFooter.
 */

'use client';

import {
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownPanelMenu,
  DropdownSubmenu,
  DropdownSubmenuContent,
  DropdownSubmenuTrigger,
} from '@octavian-tocan/react-dropdown';
import { useQueryClient } from '@tanstack/react-query';
import {
  ChevronsUpDownIcon,
  DownloadIcon,
  GiftIcon,
  GlobeIcon,
  HelpCircleIcon,
  InfoIcon,
  LayoutGridIcon,
  LogOutIcon,
  SettingsIcon,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import type * as React from 'react';
import { useCallback, useState } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { toast } from '@/lib/toast';
import { getInitials } from '@/lib/user-utils';
import { cn } from '@/lib/utils';

/**
 * Identity rendered in the trigger and the dropdown header label.
 *
 * Kept as a plain prop bag (rather than wired to an auth hook) so the
 * component remains a presentation primitive — callers fetch the user
 * however they want and pass the resolved fields down.
 */
export type NavUserIdentity = {
  /** Display name shown on the trigger row. */
  name: string;
  /** Account email shown as the dropdown's top label. */
  email: string;
  /** Subscription tier copy ("Free", "Studio plan", "Team", etc.). */
  plan: string;
  /** Optional avatar image URL; falls back to initials when missing. */
  avatar?: string;
};

const LANGUAGE_OPTIONS = [
  { id: 'en', label: 'English' },
  { id: 'es', label: 'Español' },
  { id: 'fr', label: 'Français' },
  { id: 'de', label: 'Deutsch' },
  { id: 'ja', label: '日本語' },
] as const satisfies ReadonlyArray<{ id: string; label: string }>;

const LEARN_MORE_LINKS = [
  { id: 'changelog', label: 'Changelog' },
  { id: 'docs', label: 'Documentation' },
  { id: 'community', label: 'Community' },
  { id: 'status', label: 'Status' },
] as const satisfies ReadonlyArray<{ id: string; label: string }>;

/** Stub for menu items whose actions are not yet implemented. */
function noop(): void {
  // Intentionally empty — placeholder for unimplemented menu actions.
}

/** Shared className for the Language / Learn-more submenu trigger rows. */
const SUBMENU_TRIGGER_CLASSNAME =
  'flex w-full cursor-pointer items-center gap-2 rounded-[4px] px-2 py-1.5 text-sm hover:bg-foreground/[0.04]';

/**
 * Sidebar profile button + account dropdown.
 *
 * Stays mounted while the sidebar is collapsing so the user chip rides
 * the slide animation out to the left along with the rest of the
 * sidebar contents. The previous early-return-on-collapse caused the
 * chip to vanish the instant the user clicked the toggle, before the
 * 200ms slide had even started — visually jarring.
 *
 * Uses `DropdownPanelMenu` with JSX `DropdownSubmenu` children for the
 * Language / Learn-more entries so those open as side flyouts. The
 * earlier `DropdownMenuDef`/`MenuItemDef` data-driven variant rendered
 * submenus as inline accordions, which caused a noticeable
 * "parent collapses → reopen with the sub auto-expanded" stutter
 * every time the user clicked a submenu trigger.
 *
 * @param user - Identity rendered in the trigger and dropdown header.
 */
export function NavUser({ user }: { user: NavUserIdentity }): React.JSX.Element {
  const { push, replace } = useRouter();
  const fetcher = useAuthedFetch();
  const queryClient = useQueryClient();
  // Tracks dropdown open state so we can apply the active background on the
  // trigger button — replaces Radix's automatic `aria-expanded` Tailwind variant.
  const [isOpen, setIsOpen] = useState(false);

  /**
   * Calls the FastAPI-Users logout route, clears every cached query so
   * the next session never sees the previous user's data, and routes to
   * /login. The logout endpoint clears the JWT cookie server-side; the
   * cache wipe is the client-side complement.
   */
  const handleLogout = useCallback(async (): Promise<void> => {
    try {
      await fetcher('/auth/jwt/logout', { method: 'POST' });
    } catch (error) {
      // 401 here is fine — we're logging out anyway. Anything else is
      // surfaced once but doesn't block the local cleanup.
      if (error instanceof Error && !error.message.includes('401')) {
        toast.error('Logout request failed; clearing local session.');
      }
    } finally {
      queryClient.clear();
      replace('/login');
    }
  }, [fetcher, queryClient, replace]);

  const trigger = (
    <button
      className={cn(
        'group flex w-full cursor-pointer items-center gap-2.5 rounded-[8px] p-2 text-left',
        'transition-[background-color,color] duration-150',
        'hover:bg-foreground/[0.07]',
        isOpen && 'bg-foreground/[0.09]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40'
      )}
      type="button"
    >
      <Avatar className="size-7 shrink-0">
        {user.avatar ? <AvatarImage alt={user.name} src={user.avatar} /> : null}
        <AvatarFallback className="text-xs">{getInitials(user.name)}</AvatarFallback>
      </Avatar>
      <div className="flex min-w-0 flex-1 flex-col leading-tight">
        <span className="truncate font-medium text-foreground text-sm">{user.name}</span>
        <span className="truncate text-muted-foreground text-sm">{user.plan}</span>
      </div>
      <ChevronsUpDownIcon
        aria-hidden="true"
        className="size-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground"
      />
    </button>
  );

  // Desktop relies on the parent `<ResizablePanel>`'s `overflow:hidden`
  // to clip the chip out as the panel slides to zero width — keeping
  // the component mounted lets it participate in the slide animation
  // instead of disappearing instantly.
  return (
    // Top border = the requested separator above the profile row.
    // Using `border-foreground/8` (faint) so it reads as a divider, not a
    // hard line. Wrapper gets its own padding instead of forcing the
    // trigger button to swallow it — this lets the trigger's hover paint
    // a clean fully-rounded pill that actually fills the visible row.
    <div className="shrink-0 border-foreground/8 border-t p-2">
      <DropdownPanelMenu
        // Anchor the panel's LEFT edge to the trigger's LEFT edge so it
        // grows up-and-to-the-right. The default `align="end"` (right-edge
        // anchored) overflows off-screen left because the trigger sits at
        // the very bottom-left of the viewport (sidebar footer) — the
        // menu's right edge would land mid-trigger, pushing its left
        // edge into negative X. See image #36 for the prior bug.
        align="start"
        asChild
        // `popover-styled` provides the project's themed background,
        // border, layered shadow, and global backdrop-filter blur.
        // Without it the consumer's className REPLACES the package's
        // `bg-white` default and the dropdown renders transparent —
        // letting the sidebar bleed through.
        contentClassName="popover-styled p-1 w-64"
        onOpenChange={setIsOpen}
        placement="top"
        trigger={trigger}
        usePortal
      >
        <DropdownMenuLabel className="px-2 py-1.5 font-medium text-muted-foreground text-xs">
          {user.email}
        </DropdownMenuLabel>
        <DropdownMenuItem className="justify-between" onSelect={() => push('/settings')}>
          <span className="flex items-center gap-2">
            <SettingsIcon aria-hidden="true" className="size-4" />
            Settings
          </span>
          <span className="text-muted-foreground text-xs tracking-widest">⇧⌘,</span>
        </DropdownMenuItem>
        {/*
         * Side-flyout submenu — replaces the inline-accordion variant the
         * data-driven menu used. The earlier accordion collapsed the parent
         * on click and reopened it with `language` auto-expanded, which read
         * as a UI stutter every time.
         */}
        <DropdownSubmenu>
          <DropdownSubmenuTrigger className={SUBMENU_TRIGGER_CLASSNAME}>
            <GlobeIcon aria-hidden="true" className="size-4" />
            <span className="flex-1 text-left">Language</span>
          </DropdownSubmenuTrigger>
          <DropdownSubmenuContent className="popover-styled min-w-44 p-1">
            {LANGUAGE_OPTIONS.map((opt) => (
              <DropdownMenuItem key={opt.id} onSelect={noop}>
                {opt.label}
              </DropdownMenuItem>
            ))}
          </DropdownSubmenuContent>
        </DropdownSubmenu>
        <DropdownMenuItem onSelect={noop}>
          <HelpCircleIcon aria-hidden="true" className="size-4" />
          Get help
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={noop}>
          <LayoutGridIcon aria-hidden="true" className="size-4" />
          View all plans
        </DropdownMenuItem>
        <DropdownMenuItem disabled onSelect={noop}>
          <DownloadIcon aria-hidden="true" className="size-4" />
          Get apps and extensions
        </DropdownMenuItem>
        <DropdownMenuItem disabled onSelect={noop}>
          <GiftIcon aria-hidden="true" className="size-4" />
          Gift Pawrrtal
        </DropdownMenuItem>
        <DropdownSubmenu>
          {/* `disabled` was previously a `DropdownSubmenuTrigger` prop;
					    the lib dropped it.  Visual disabled state via class until
					    the lib re-adds support — click still opens but the
					    aria + opacity tell the user it's a placeholder. */}
          <DropdownSubmenuTrigger
            aria-disabled
            className={cn(SUBMENU_TRIGGER_CLASSNAME, 'pointer-events-none opacity-50')}
          >
            <InfoIcon aria-hidden="true" className="size-4" />
            <span className="flex-1 text-left">Learn more</span>
          </DropdownSubmenuTrigger>
          <DropdownSubmenuContent className="popover-styled min-w-44 p-1">
            {LEARN_MORE_LINKS.map((link) => (
              <DropdownMenuItem disabled key={link.id} onSelect={noop}>
                {link.label}
              </DropdownMenuItem>
            ))}
          </DropdownSubmenuContent>
        </DropdownSubmenu>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            void handleLogout();
          }}
        >
          <LogOutIcon aria-hidden="true" className="size-4" />
          Log out
        </DropdownMenuItem>
      </DropdownPanelMenu>
    </div>
  );
}
