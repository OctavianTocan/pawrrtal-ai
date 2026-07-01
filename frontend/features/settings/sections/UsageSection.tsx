'use client';

import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { SettingsCard, SettingsPage, SettingsRow, SettingsSectionHeader } from '../primitives';

/** A single usage limit row with a horizontal "amount left" bar. */
function UsageLimitRow({
  label,
  resetLabel,
  percentLeft,
}: {
  label: string;
  resetLabel: string;
  percentLeft: number;
}): React.JSX.Element {
  const clamped = Math.max(0, Math.min(100, percentLeft));
  return (
    <SettingsRow description={resetLabel} label={<span className="text-foreground text-sm">{label}</span>}>
      <div className="flex items-center gap-3">
        <div className="h-1 w-32 overflow-hidden rounded-full bg-foreground/10">
          <div className={cn('h-full bg-foreground/85')} style={{ width: `${clamped}%` }} />
        </div>
        <span className="w-16 text-right text-muted-foreground text-xs tabular-nums">{clamped}% left</span>
      </div>
    </SettingsRow>
  );
}

/**
 * Visual-only Usage settings section.
 *
 * Mirrors the reference layout: a "General usage limits" card with a 5h
 * + weekly bar, a per-model card (placeholder for whatever model the
 * user is on), and a Credit panel with Purchase + Auto-reload Settings.
 * No real telemetry yet — the bars use static placeholder percentages.
 */
export function UsageSection(): React.JSX.Element {
  return (
    <SettingsPage description="Track your active limits, per-model usage, and credit balance." title="Usage">
      <SettingsCard>
        <SettingsSectionHeader description="Usage limits applied across every model." title="General usage limits" />
        <UsageLimitRow label="5 hour usage limit" percentLeft={100} resetLabel="Resets 4:15 AM" />
        <UsageLimitRow label="Weekly usage limit" percentLeft={38} resetLabel="Resets 7:51 AM" />
      </SettingsCard>

      <SettingsCard>
        <SettingsSectionHeader
          description="Limits scoped to the model you're currently using."
          title="Claude Opus 4.7 usage limits"
        />
        <UsageLimitRow label="5 hour usage limit" percentLeft={100} resetLabel="Resets 4:15 AM" />
        <UsageLimitRow label="Weekly usage limit" percentLeft={96} resetLabel="Resets May 10" />
      </SettingsCard>

      <SettingsCard>
        <SettingsSectionHeader description="Top up to keep messaging when usage limits are reached." title="Credit" />
        <SettingsRow description="Use credit to send messages when you reach usage limits." label="0 credit remaining">
          <Button size="sm" type="button" variant="secondary">
            Purchase
          </Button>
        </SettingsRow>
        <SettingsRow
          description="Automatically add credit when you reach your minimum balance."
          label="Auto-reload credit"
        >
          <Button size="sm" type="button" variant="secondary">
            Settings
          </Button>
        </SettingsRow>
      </SettingsCard>
    </SettingsPage>
  );
}
