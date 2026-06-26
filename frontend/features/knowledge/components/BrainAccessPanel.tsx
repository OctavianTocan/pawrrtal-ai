'use client';

/**
 * Brain access sub-view.
 *
 * Top: a card inviting another user to access this workspace's brain — avatar
 * with a plus, heading, description, and an email + permission picker row.
 * Below: tabs that switch between "Shared by me" and "Shared with me",
 * each currently showing the same empty state.
 */

import { ChevronDownIcon, PlusIcon, UserIcon, UsersIcon } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import { cn } from '@/lib/utils';
import { EmptyState } from './EmptyState';

type BrainAccessTabId = 'shared-by-me' | 'shared-with-me';

interface BrainAccessTabProps {
  tabId: BrainAccessTabId;
  label: string;
  activeTab: BrainAccessTabId;
  onSelect: (tab: BrainAccessTabId) => void;
}

function BrainAccessTab({ tabId, label, activeTab, onSelect }: BrainAccessTabProps): ReactNode {
  const isActive = tabId === activeTab;
  return (
    <button
      type="button"
      onClick={() => onSelect(tabId)}
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'cursor-pointer rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors duration-150 ease-out',
        isActive
          ? 'bg-foreground-5 text-foreground'
          : 'text-muted-foreground hover:bg-foreground-5 hover:text-foreground'
      )}
    >
      {label}
    </button>
  );
}

/**
 * Container-light component — owns the local active-tab state because no
 * other surface in the app cares about it. URL persistence isn't needed
 * since both tabs currently surface the same empty state.
 */
export function BrainAccessPanel(): ReactNode {
  const [activeTab, setActiveTab] = useState<BrainAccessTabId>('shared-by-me');

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Invite card */}
      <section className="rounded-[14px] border border-border bg-background-elevated p-5 shadow-minimal">
        <div className="flex items-start gap-4">
          <span className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-foreground-5 text-muted-foreground">
            <UserIcon aria-hidden="true" className="size-5" />
            <span className="absolute -right-1 -bottom-1 flex size-4 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-background">
              <PlusIcon aria-hidden="true" className="size-2.5" />
            </span>
          </span>
          <div className="flex flex-1 flex-col gap-1">
            <h3 className="font-display text-[16px] font-medium text-foreground">Share brain access</h3>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              Invite teammates to your workspace. They can read your saved files, memory, and skills. You control the
              level of access.
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            aria-label="Invite email address"
            type="email"
            placeholder="email@example.com"
            className="h-9 flex-1 min-w-[200px] cursor-text rounded-md border border-border bg-background px-3 text-[13px] text-foreground outline-none transition-colors duration-150 placeholder:text-muted-foreground focus-visible:border-ring"
          />
          <button
            type="button"
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-background px-3 text-[13px] font-medium text-foreground transition-colors duration-150 ease-out hover:bg-foreground-5"
          >
            Read only
            <ChevronDownIcon aria-hidden="true" className="size-3.5" />
          </button>
          <button
            type="button"
            className="inline-flex h-9 cursor-pointer items-center rounded-md bg-foreground px-4 text-[13px] font-medium text-background transition-colors duration-150 ease-out hover:bg-foreground/90"
          >
            Invite
          </button>
        </div>
      </section>

      {/* Tabs */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-1">
          <BrainAccessTab tabId="shared-by-me" label="Shared by me" activeTab={activeTab} onSelect={setActiveTab} />
          <BrainAccessTab tabId="shared-with-me" label="Shared with me" activeTab={activeTab} onSelect={setActiveTab} />
        </div>

        <div className="min-h-[280px]">
          <EmptyState
            icon={UsersIcon}
            title={
              activeTab === 'shared-by-me' ? 'You haven’t shared your workspace yet.' : 'Nothing shared with you yet.'
            }
            description={
              activeTab === 'shared-by-me'
                ? 'Invite a teammate above to give them access to your workspace brain.'
                : 'When someone shares their workspace with you, it’ll show up here.'
            }
          />
        </div>
      </section>
    </div>
  );
}
