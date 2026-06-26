'use client';

import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { useWhimsyTile } from '@/features/whimsy';
import { cn } from '@/lib/utils';
import { SETTINGS_SECTIONS, type SettingsSectionId } from './constants';
import { AppearanceSection } from './sections/AppearanceSection';
import { ArchivedChatsSection } from './sections/ArchivedChatsSection';
import { ChannelsSection } from './sections/ChannelsSection';
import { GeneralSection } from './sections/GeneralSection';
import { IntegrationsSection } from './sections/IntegrationsSection';
import { PersonalizationSection } from './sections/PersonalizationSection';
import { PlaceholderSection } from './sections/PlaceholderSection';
import { PluginsSection } from './sections/PluginsSection';
import { UsageSection } from './sections/UsageSection';
import { WorkspacesSection } from './sections/WorkspacesSection';

/**
 * Right-pane body for the currently selected section. Lookup-table-shaped so
 * adding a new section means: register a row in `SETTINGS_SECTIONS`, then add a
 * case here. Anything not yet wired falls through to `PlaceholderSection`.
 */
function ActiveSettingsSection({ activeId }: { activeId: SettingsSectionId }): React.JSX.Element {
  if (activeId === 'general') return <GeneralSection />;
  if (activeId === 'workspaces') return <WorkspacesSection />;
  if (activeId === 'appearance') return <AppearanceSection />;
  if (activeId === 'personalization') return <PersonalizationSection />;
  if (activeId === 'integrations') return <IntegrationsSection />;
  if (activeId === 'plugins') return <PluginsSection />;
  if (activeId === 'channels') return <ChannelsSection />;
  if (activeId === 'archived-chats') return <ArchivedChatsSection />;
  if (activeId === 'usage') return <UsageSection />;
  const section = SETTINGS_SECTIONS.find((entry) => entry.id === activeId);
  return <PlaceholderSection title={section?.label ?? 'Settings'} />;
}

/**
 * Renders the same texture overlay the chat panel uses, scoped to its
 * positioned parent (here, the settings ``<main>``). Pulled out as a
 * component so the hook subscribes once for the panel and so the parent
 * stays JSX-clean. Returns ``null`` when the user has disabled whimsy.
 */
function SettingsWhimsyOverlay(): React.JSX.Element | null {
  const whimsy = useWhimsyTile();
  if (!whimsy.cssUrl) return null;
  return (
    <>
      {whimsy.backgroundColor ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ backgroundColor: whimsy.backgroundColor }}
        />
      ) : null}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 text-foreground [mask-repeat:repeat] [-webkit-mask-repeat:repeat]"
        style={{
          backgroundColor: whimsy.tintColor,
          opacity: whimsy.opacity,
          maskImage: whimsy.cssUrl,
          WebkitMaskImage: whimsy.cssUrl,
          maskSize: whimsy.maskSize,
          WebkitMaskSize: whimsy.maskSize,
        }}
      />
    </>
  );
}

/**
 * Two-pane settings shell: left rail with section list, right pane with the
 * active section's body. Visually mirrors the Codex reference settings page.
 *
 * Ships its own layout (no chat sidebar) — mounted at `/settings` outside
 * the `(app)` route group on purpose so the wider chat chrome doesn't bleed
 * through.
 */
export function SettingsLayout(): React.JSX.Element {
  const { push } = useRouter();
  const [activeId, setActiveId] = useState<SettingsSectionId>('general');

  return (
    <div className="grid h-svh w-full grid-cols-[260px_1fr] bg-sidebar">
      {/* Left rail — slightly looser vertical rhythm than the chat
			    sidebar (gap-4 vs gap-2) so the section list reads like a
			    settings nav, not a project list. The rail divider uses
			    `border-border/60` so it tints itself per active theme
			    instead of stamping a hard `foreground/8` line. */}
      <aside className="sidepanel-text-scope flex h-full flex-col gap-4 overflow-y-auto border-r border-border/60 px-3 pb-4 pt-4">
        <button
          className="flex w-full cursor-pointer items-center gap-2 rounded-[8px] px-2 py-1.5 text-sm text-muted-foreground transition-colors duration-150 hover:bg-foreground/[0.05] hover:text-foreground"
          onClick={() => push('/')}
          type="button"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          <span>Back to app</span>
        </button>
        <nav className="flex flex-col gap-0.5">
          {SETTINGS_SECTIONS.map((section) => {
            const isActive = activeId === section.id;
            return (
              <button
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'group flex cursor-pointer items-center gap-2.5 rounded-[8px] px-2.5 py-1.5 text-left text-sm transition-colors duration-150',
                  isActive
                    ? 'bg-foreground/[0.08] font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground'
                )}
                key={section.id}
                onClick={() => setActiveId(section.id)}
                type="button"
              >
                <section.Icon
                  aria-hidden="true"
                  className={cn('size-4 shrink-0', isActive ? 'text-foreground' : 'text-muted-foreground')}
                />
                <span className="truncate">{section.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/*
       * Mirror the chat panel's whimsy texture overlay on the right
       * pane so editing the texture knobs in Settings → Appearance
       * gives immediate, visible feedback. Sidebar deliberately does
       * NOT receive the overlay — it stays a flat surface so
       * navigation chrome reads cleanly.
       *
       * The overlay is the viewport-sized sibling of a separately
       * scrolling inner box. If the overlay were ``inset-0`` inside
       * an ``overflow-y: auto`` parent, the absolute box would
       * resolve to the parent's padding box (one viewport tall) and
       * scroll away with the content — leaving the texture only at
       * the top of the page. Splitting the scroll into an inner
       * ``absolute inset-0 overflow-y-auto`` lets the overlay stay
       * pinned to the visible area while content scrolls underneath.
       */}
      <main className="relative h-full bg-background">
        <SettingsWhimsyOverlay />
        <div className="absolute inset-0 overflow-y-auto p-10">
          <div className="relative mx-auto w-full max-w-3xl">
            <ActiveSettingsSection activeId={activeId} />
          </div>
        </div>
      </main>
    </div>
  );
}
