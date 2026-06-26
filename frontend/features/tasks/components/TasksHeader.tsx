'use client';

/**
 * Top-of-page header for the Tasks surface.
 *
 * Houses the editorial title (`Today` etc.) on the left set in Newsreader
 * display, the secondary count, and the right-side "Display" pill. Stays
 * pure — the container picks the title, count, and action set.
 */

import { Settings2Icon } from 'lucide-react';
import type { ReactNode } from 'react';

export interface TasksHeaderProps {
  /** Display title — set in `font-display` (Newsreader). */
  title: string;
  /** Secondary count line shown under the title (e.g. `22 tasks`). */
  subtitle: string;
  /**
   * Optional view-switcher segment rendered to the right (e.g. layout
   * picker). The container passes a fully-rendered node so the header
   * stays decoupled from the picker's internal state.
   */
  rightSlot?: ReactNode;
}

/**
 * Pure presentation. Both the title and subtitle are pre-resolved by the
 * container so this component never reaches into URL params or mock data.
 */
export function TasksHeader({ title, subtitle, rightSlot }: TasksHeaderProps): ReactNode {
  return (
    <header className="flex items-end justify-between gap-3 px-6 pt-7 pb-4">
      <div className="min-w-0">
        <h1 className="font-display text-[40px] leading-none font-medium tracking-[-0.025em] text-balance text-foreground">
          {title}
        </h1>
        <p className="mt-2 text-[13px] tabular-nums text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2 pb-1">
        {rightSlot}
        <button
          type="button"
          aria-label="Tasks settings"
          className="flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 ease-out hover:bg-foreground/[0.05] hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
        >
          <Settings2Icon aria-hidden="true" className="size-4" strokeWidth={2.25} />
        </button>
      </div>
    </header>
  );
}
