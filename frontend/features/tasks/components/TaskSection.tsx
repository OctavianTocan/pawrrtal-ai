'use client';

/**
 * Collapsible task group rendered between the page header and the next
 * section. Owns its own collapsed-arrow rotation and the right-aligned
 * action affordance (e.g. "Reschedule" on the Overdue section).
 *
 * The section is collapsible-only — completion, selection, and toggle
 * callbacks all flow through `children` (rendered by the container).
 */

import { ChevronRightIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { TaskSectionData } from '../types';

export interface TaskSectionProps {
  section: TaskSectionData;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** Pre-rendered task rows for this section. */
  children: ReactNode;
}

/**
 * Pure presentation. The container picks the children (so it controls
 * which row component renders) and the collapsed boolean (persisted in
 * `localStorage`).
 */
export function TaskSection({ section, collapsed, onToggleCollapsed, children }: TaskSectionProps): ReactNode {
  const headingTone = section.tone === 'destructive' ? 'text-destructive-text' : 'text-foreground';
  const taskCountLabel = `${section.tasks.length} ${section.tasks.length === 1 ? 'task' : 'tasks'}`;

  return (
    <section className="border-b border-foreground/[0.08]">
      <header className="flex items-center justify-between gap-3 py-2 pr-3 pl-1">
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-expanded={!collapsed}
          className="group/header flex flex-1 cursor-pointer items-center gap-2 rounded-md py-1 pl-1 text-left transition-colors duration-150 ease-out hover:bg-foreground/[0.03] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
        >
          <ChevronRightIcon
            aria-hidden="true"
            className={cn(
              'size-3.5 shrink-0 text-muted-foreground transition-transform duration-150 ease-out motion-reduce:transition-none',
              collapsed ? 'rotate-0' : 'rotate-90'
            )}
            strokeWidth={2.5}
          />
          <h2 className={cn('text-[13px] font-semibold tracking-tight tabular-nums', headingTone)}>{section.label}</h2>
          {section.subtitle ? (
            <span className="text-[12px] font-normal text-muted-foreground">{section.subtitle}</span>
          ) : null}
          <span aria-hidden="true" className="text-[11px] font-medium tabular-nums text-muted-foreground/70">
            ·
          </span>
          <span className="text-[12px] font-medium tabular-nums text-muted-foreground">{taskCountLabel}</span>
        </button>
        {section.rightAction ? (
          <button
            type="button"
            onClick={section.rightAction.onClick}
            className="cursor-pointer text-[12px] font-medium text-accent transition-opacity duration-150 ease-out hover:opacity-80 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40"
          >
            {section.rightAction.label}
          </button>
        ) : null}
      </header>
      {/*
       * `grid-template-rows` 1fr/0fr animates to/from "auto" without the
       * usual height-animation jank. Pairs with overflow-hidden inside.
       *
       * Timing follows DESIGN.md → Motion → Open / close timing for
       * overlay-class surfaces: 140 ms ease-out-expo on open, 100 ms
       * ease-in-quint on close. Open is "reveal slowly enough to read";
       * close is "get out of my way." Symmetrical timing reads as bouncy.
       */}
      <div
        className={cn(
          'grid transition-[grid-template-rows] motion-reduce:transition-none',
          collapsed ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'
        )}
        style={{
          transitionDuration: collapsed ? '100ms' : '140ms',
          transitionTimingFunction: collapsed ? 'cubic-bezier(0.7, 0, 0.84, 0)' : 'cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </section>
  );
}
