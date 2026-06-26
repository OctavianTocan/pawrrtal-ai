'use client';

import { ChevronDown, Plus, Search, Settings as SettingsIcon, X } from 'lucide-react';
import type * as React from 'react';
import { useState } from 'react';
import { AppDialog } from '@/components/ui/app-dialog';
import { cn } from '@/lib/utils';
import { type CatalogIntegration, INTEGRATION_CATALOG } from './catalog';

/** Props for {@link AddIntegrationModal}. */
export interface AddIntegrationModalProps {
  open: boolean;
  onDismiss: () => void;
  onAddCustom: () => void;
}

/**
 * Modal that lets the user browse + connect available integrations.
 *
 * Visual-only today: the search field filters the catalog list, and the
 * "Connect" buttons mark the row as connected in local state. Clicking
 * "+ Add custom" opens the {@link AddCustomMcpModal}.
 */
export function AddIntegrationModal({ open, onDismiss, onAddCustom }: AddIntegrationModalProps): React.JSX.Element {
  const [query, setQuery] = useState('');
  const filtered = INTEGRATION_CATALOG.filter((entry) => entry.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <AppDialog
      ariaLabel="Add integrations"
      onDismiss={onDismiss}
      open={open}
      showDismissButton={false}
      size="lg"
      testId="add-integration-modal"
    >
      <div className="flex flex-col gap-4 p-6">
        <header className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Add integrations</h2>
          <button
            aria-label="Close"
            className="rounded-[6px] p-1.5 text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
            onClick={onDismiss}
            type="button"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="flex items-center gap-2">
          <div className="relative flex flex-1 items-center">
            <Search aria-hidden="true" className="absolute left-2.5 size-4 text-muted-foreground" />
            <input
              aria-label="Search integrations"
              className="h-9 w-full rounded-[8px] border border-foreground/10 bg-foreground/[0.03] py-1 pr-3 pl-8 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search integrations..."
              value={query}
            />
          </div>
          <button
            className="flex h-9 items-center gap-1 rounded-[8px] border border-foreground/10 bg-foreground/[0.03] px-2.5 text-xs text-foreground hover:bg-foreground/[0.06]"
            type="button"
          >
            All
            <ChevronDown className="size-3.5" />
          </button>
          <button
            className="flex h-9 items-center gap-1 rounded-[8px] border border-foreground/15 bg-foreground px-3 text-xs font-medium text-background hover:bg-foreground/85"
            onClick={onAddCustom}
            type="button"
          >
            <Plus className="size-3.5" />
            Add custom
          </button>
        </div>

        <div className="grid max-h-[60dvh] grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
          {filtered.map((entry) => (
            <CatalogTile entry={entry} key={entry.id} />
          ))}
        </div>
      </div>
    </AppDialog>
  );
}

/** Single tile inside the catalog grid. */
function CatalogTile({ entry }: { entry: CatalogIntegration }): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-3 rounded-[10px] border border-foreground/10 bg-foreground/[0.02] p-3">
      <div className="flex items-start gap-2.5">
        <span
          aria-hidden="true"
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-[8px]',
            entry.tileBgClass,
            entry.tileTextClass
          )}
        >
          <entry.Icon className="size-4" />
        </span>
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-medium text-foreground">{entry.name}</span>
          <span className="line-clamp-2 text-[11px] text-muted-foreground">{entry.description}</span>
        </div>
      </div>
      {entry.state === 'installed' ? (
        <button
          aria-label={`Settings for ${entry.name}`}
          className="rounded-[6px] p-1.5 text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
          type="button"
        >
          <SettingsIcon className="size-3.5" />
        </button>
      ) : (
        <button
          className="rounded-[7px] border border-foreground/10 bg-foreground/[0.04] px-2.5 py-1 text-xs font-medium text-foreground hover:bg-foreground/[0.08]"
          type="button"
        >
          Connect
        </button>
      )}
    </div>
  );
}
