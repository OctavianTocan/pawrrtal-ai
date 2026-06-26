'use client';

import { Plus } from 'lucide-react';
import type * as React from 'react';
import { useState } from 'react';
import { AddCustomMcpModal } from '../integrations/AddCustomMcpModal';
import { AddIntegrationModal } from '../integrations/AddIntegrationModal';
import { YOUR_INTEGRATIONS } from '../integrations/catalog';
import { IntegrationRow } from '../integrations/IntegrationRow';
import { SettingsCard, SettingsPage, SettingsSectionHeader } from '../primitives';

/**
 * Integrations settings section.
 *
 * UI shell is in place but no integrations are implemented yet in the
 * backend. The notice below makes that explicit so the section doesn't
 * mislead users into thinking Apple Calendar / Gmail / Drive / etc are
 * already connected.
 */
export function IntegrationsSection(): React.JSX.Element {
  const [showCatalog, setShowCatalog] = useState(false);
  const [showCustomMcp, setShowCustomMcp] = useState(false);

  return (
    <SettingsPage
      description="Connect Pawrrtal to your tools so it can read context and run actions."
      title="Integrations"
    >
      <div className="rounded-[10px] border border-amber-500/30 bg-amber-500/10 px-3.5 py-3 text-sm text-amber-200">
        <div className="font-semibold">Coming soon</div>
        <div className="text-xs text-amber-200/80 mt-0.5">
          This UI is in place, but no integrations are wired up yet. Connecting Gmail, Calendar, Drive, etc. will arrive
          in future releases.
        </div>
      </div>

      <SettingsCard>
        <SettingsSectionHeader
          actions={
            <button
              className="flex cursor-pointer items-center gap-1.5 rounded-[8px] border border-foreground/15 bg-foreground/[0.04] px-3 py-1.5 text-xs font-medium text-foreground transition-colors duration-150 ease-out hover:bg-foreground/[0.08]"
              onClick={() => setShowCatalog(true)}
              type="button"
            >
              <Plus className="size-3.5" />
              Add integration
            </button>
          }
          description="Apps and services Pawrrtal is currently connected to."
          title="Your integrations"
        />
        {YOUR_INTEGRATIONS.length === 0 ? (
          <div className="pt-3 text-sm text-muted-foreground">No integrations connected yet.</div>
        ) : (
          <div className="flex flex-col gap-2 pt-3">
            {YOUR_INTEGRATIONS.map((integration) => (
              <IntegrationRow integration={integration} key={integration.id} />
            ))}
          </div>
        )}
      </SettingsCard>

      <AddIntegrationModal
        onAddCustom={() => {
          setShowCatalog(false);
          setShowCustomMcp(true);
        }}
        onDismiss={() => setShowCatalog(false)}
        open={showCatalog}
      />
      <AddCustomMcpModal
        onContinue={() => setShowCustomMcp(false)}
        onDismiss={() => setShowCustomMcp(false)}
        open={showCustomMcp}
      />
    </SettingsPage>
  );
}
