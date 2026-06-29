'use client';

import { ChevronDown, ChevronUp, Pencil, Plus, Settings as SettingsIcon } from 'lucide-react';
import type * as React from 'react';
import { useState } from 'react';
import { AppPill } from '@/components/ui/app-pill';
import { cn } from '@/lib/utils';
import type { IntegrationAccount, IntegrationBadge, IntegrationDef } from './catalog';

/** Renders a single integration row + (optional) collapsible per-account list. */
export function IntegrationRow({ integration }: { integration: IntegrationDef }): React.JSX.Element {
  const hasAccounts = (integration.accounts?.length ?? 0) > 0;
  const [expanded, setExpanded] = useState(true);

  const headerInner = (
    <div className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className={cn(
          'flex size-9 shrink-0 items-center justify-center rounded-[8px]',
          integration.tileBgClass,
          integration.tileTextClass
        )}
      >
        <integration.Icon className="size-4" />
      </span>
      <div className="flex min-w-0 flex-col">
        <span className="flex items-center gap-2 font-medium text-foreground text-sm">
          {integration.name}
          {integration.badge ? <IntegrationBadgePill badge={integration.badge} /> : null}
        </span>
        <span className="truncate text-muted-foreground text-xs">{integration.description}</span>
      </div>
    </div>
  );

  if (!hasAccounts) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-[10px] border border-foreground/10 bg-foreground/[0.02] px-3 py-2.5">
        {headerInner}
        <button
          aria-label={`Settings for ${integration.name}`}
          className="rounded-[6px] p-1.5 text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
          type="button"
        >
          <SettingsIcon className="size-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0 rounded-[10px] border border-foreground/10 bg-foreground/[0.02]">
      <button
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-foreground/[0.03]"
        onClick={() => setExpanded((prev) => !prev)}
        type="button"
      >
        {headerInner}
        <span className="rounded-[6px] p-1 text-muted-foreground">
          {expanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </span>
      </button>
      {expanded ? (
        <div className="flex flex-col gap-0 border-foreground/8 border-t px-3 py-1">
          {integration.accounts?.map((account) => (
            <IntegrationAccountRow account={account} key={account.id} />
          ))}
          <button
            className="mt-1 flex items-center gap-2 rounded-[6px] px-1 py-2 text-muted-foreground text-xs transition-colors hover:bg-foreground/[0.04] hover:text-foreground"
            type="button"
          >
            <Plus className="size-3.5" />
            Add another account
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Single account row inside an expanded integration block. */
function IntegrationAccountRow({ account }: { account: IntegrationAccount }): React.JSX.Element {
  const isConnected = account.status === 'connected';
  return (
    <div className="flex items-center justify-between gap-3 border-foreground/5 border-b py-2 last:border-0">
      <div className="flex min-w-0 items-center gap-2 text-sm">
        {account.label ? <span className="text-muted-foreground">{account.label}</span> : null}
        <span className="truncate text-foreground">{account.email}</span>
        {account.subtitle && account.subtitle !== account.email ? (
          <span className="truncate text-muted-foreground">{account.subtitle}</span>
        ) : null}
        <IntegrationBadgePill badge={isConnected ? 'connected' : 'expired'} />
      </div>
      <div className="flex items-center gap-1">
        <button
          aria-label={`Rename ${account.email}`}
          className="rounded-[6px] p-1.5 text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
          type="button"
        >
          <Pencil className="size-3.5" />
        </button>
        <button
          aria-label={`Settings for ${account.email}`}
          className="rounded-[6px] p-1.5 text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
          type="button"
        >
          <SettingsIcon className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

/** Compact pill rendered next to an integration / account name. */
function IntegrationBadgePill({ badge }: { badge: NonNullable<IntegrationBadge> }): React.JSX.Element {
  const label = badge === 'beta' ? 'Beta' : badge === 'connected' ? 'Connected' : 'Expired';
  const tone = badge === 'beta' ? 'neutral' : badge === 'connected' ? 'success' : 'warning';
  return (
    <AppPill shape="pill" tone={tone}>
      {label}
    </AppPill>
  );
}
