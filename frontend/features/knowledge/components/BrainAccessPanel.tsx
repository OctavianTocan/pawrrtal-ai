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
import type { ReactNode } from 'react';
import { useState } from 'react';
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
      aria-current={isActive ? 'page' : undefined}
      className={cn(
        'cursor-pointer rounded-md px-3 py-1.5 font-medium text-[13px] transition-colors duration-150 ease-out',
        isActive
          ? 'bg-foreground-5 text-foreground'
          : 'text-muted-foreground hover:bg-foreground-5 hover:text-foreground'
      )}
      onClick={() => onSelect(tabId)}
      type="button"
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
            <span className="absolute -right-1 -bottom-1 flex size-4 items-center justify-center rounded-full bg-accent font-bold text-[10px] text-background">
              <PlusIcon aria-hidden="true" className="size-2.5" />
            </span>
          </span>
          <div className="flex flex-1 flex-col gap-1">
            <h3 className="font-display font-medium text-[16px] text-foreground">Share brain access</h3>
            <p className="text-[13px] text-muted-foreground leading-relaxed">
              Invite teammates to your workspace. They can read your saved files, memory, and skills. You control the
              level of access.
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            aria-label="Invite email address"
            className="h-9 min-w-[200px] flex-1 cursor-text rounded-md border border-border bg-background px-3 text-[13px] text-foreground outline-none transition-colors duration-150 placeholder:text-muted-foreground focus-visible:border-ring"
            placeholder="email@example.com"
            type="email"
          />
          <button
            className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-background px-3 font-medium text-[13px] text-foreground transition-colors duration-150 ease-out hover:bg-foreground-5"
            type="button"
          >
            Read only
            <ChevronDownIcon aria-hidden="true" className="size-3.5" />
          </button>
          <button
            className="inline-flex h-9 cursor-pointer items-center rounded-md bg-foreground px-4 font-medium text-[13px] text-background transition-colors duration-150 ease-out hover:bg-foreground/90"
            type="button"
          >
            Invite
          </button>
        </div>
      </section>

      {/* Tabs */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-1">
          <BrainAccessTab activeTab={activeTab} label="Shared by me" onSelect={setActiveTab} tabId="shared-by-me" />
          <BrainAccessTab activeTab={activeTab} label="Shared with me" onSelect={setActiveTab} tabId="shared-with-me" />
        </div>

        <div className="min-h-[280px]">
          <EmptyState
            description={
              activeTab === 'shared-by-me'
                ? 'Invite a teammate above to give them access to your workspace brain.'
                : 'When someone shares their workspace with you, it’ll show up here.'
            }
            icon={UsersIcon}
            title={
              activeTab === 'shared-by-me' ? 'You haven’t shared your workspace yet.' : 'Nothing shared with you yet.'
            }
          />
        </div>
      </section>
    </div>
  );
}
