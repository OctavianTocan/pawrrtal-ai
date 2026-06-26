'use client';

import { XIcon } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type * as React from 'react';
import { useState } from 'react';
import { GitHubIcon } from '@/components/brand-icons/GitHubIcon';
import { GoogleDriveIcon } from '@/components/brand-icons/GoogleDriveIcon';
import { LinearIcon } from '@/components/brand-icons/LinearIcon';
import { NotionIcon } from '@/components/brand-icons/NotionIcon';
import { SlackIcon } from '@/components/brand-icons/SlackIcon';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** Settings sub-page that owns integrations management. */
const INTEGRATIONS_HREF = '/settings/integrations';

type BrandIconComponent = (props: { className?: string }) => React.JSX.Element;

type ConnectAppEntry = {
  id: string;
  label: string;
  /** Brand icon component — pulled from `components/brand-icons/`. */
  Icon: BrandIconComponent;
  /** Optional Tailwind text class to color a single-color brand glyph. */
  colorClass?: string;
};

const CONNECT_APPS: ReadonlyArray<ConnectAppEntry> = [
  { id: 'notion', label: 'Notion', Icon: NotionIcon, colorClass: 'text-foreground' },
  { id: 'slack', label: 'Slack', Icon: SlackIcon },
  { id: 'google-drive', label: 'Google Drive', Icon: GoogleDriveIcon },
  { id: 'github', label: 'GitHub', Icon: GitHubIcon, colorClass: 'text-foreground' },
  { id: 'linear', label: 'Linear', Icon: LinearIcon, colorClass: 'text-[#5e6ad2]' },
];

/** Props for the {@link ConnectAppsStrip} component. */
export type ConnectAppsStripProps = {
  /** Additional classes for the root strip container. */
  className?: string;
  /** Optional callback fired after the user dismisses the strip. */
  onDismiss?: () => void;
};

/**
 * Compact, dismissible band that renders BEHIND the chat composer and peeks
 * out below it. The component is now a standalone rounded `<div>` (not an
 * `InputGroupAddon`) so it can be siblings with the `PromptInput` above it
 * in `ChatComposer`, with a negative top margin sliding the upper portion
 * under the composer's rounded shell — that's what produces the "this
 * strip is layered under the chat box and pokes out at the bottom" depth
 * effect.
 *
 * Uses real brand-color icons (per AGENTS.md icon rule, each lives in its
 * own file under `components/brand-icons/`) so the strip reads as a
 * recognisable lineup of integrations rather than abstract Lucide glyphs.
 *
 * Layout contract (consumer-managed):
 * - Wrap `<PromptInput>` and `<ConnectAppsStrip>` in a `relative` parent.
 * - The PromptInput should sit on a higher z-index (e.g. `relative z-10`)
 *   and have a solid background (`bg-[color:var(--background-elevated)]`).
 * - This strip handles its own negative margin + `z-0`, so the consumer
 *   only has to render it after the PromptInput in the parent flex/column.
 */
export function ConnectAppsStrip({ className, onDismiss }: ConnectAppsStripProps): React.JSX.Element | null {
  const [isDismissed, setIsDismissed] = useState(false);
  const { push } = useRouter();

  const handleDismiss = (event: React.MouseEvent<HTMLButtonElement>): void => {
    event.stopPropagation();
    setIsDismissed(true);
    onDismiss?.();
  };

  const goToIntegrations = (): void => {
    push(INTEGRATIONS_HREF);
  };

  return (
    // `-mt-4` slides the strip up so its top portion is hidden under
    // the composer's rounded shell. `pt-5` gives the matching breathing
    // room to the visible content. `relative z-0` keeps it under the
    // composer (`z-10` on the PromptInput in `ChatComposer`).
    // `rounded-surface-lg` matches the composer's corner radius so the
    // visible bottom of the strip echoes the composer's geometry.
    //
    <div
      className={cn(
        'relative z-0 -mt-4 flex items-center justify-between gap-3 rounded-surface-lg bg-[color:var(--background-elevated-shade)] px-3 pt-5 pb-1 font-normal shadow-minimal transition-colors hover:bg-foreground/[0.04]',
        isDismissed && 'hidden',
        className
      )}
    >
      <p className="min-w-0 truncate text-xs text-muted-foreground">Connect your apps to get better answers</p>
      {/* Tightest grouping: `size-6` (24px) hit targets with `size-3`
			    (12px) glyphs so the lineup reads as one cluster of brand
			    chips instead of spaced affordances. */}
      <div className="-mr-1 flex shrink-0 items-center gap-0">
        {CONNECT_APPS.map((app) => (
          <Tooltip key={app.id}>
            <TooltipTrigger asChild>
              <button
                aria-label={`Connect ${app.label}`}
                className={cn(
                  'flex size-6 cursor-pointer items-center justify-center rounded-md transition-colors hover:bg-foreground/[0.06]',
                  app.colorClass ?? 'text-foreground'
                )}
                onClick={(event) => {
                  event.stopPropagation();
                  goToIntegrations();
                }}
                type="button"
              >
                <app.Icon className="size-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="top">{app.label}</TooltipContent>
          </Tooltip>
        ))}
        <button
          aria-label="Dismiss connect apps strip"
          className="ml-0.5 flex size-6 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
          onClick={handleDismiss}
          type="button"
        >
          <XIcon aria-hidden="true" className="size-3" />
        </button>
      </div>
    </div>
  );
}
