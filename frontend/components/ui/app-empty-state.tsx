/**
 * Shared empty-state layouts for sidebar, full-page, card, and settings-panel surfaces.
 *
 * Tones encode the visual recipes that previously drifted across features (mixed
 * radii, type scales, CTA shapes). Prefer **`rounded-soft`** / **`rounded-control`**
 * from the design tokens over arbitrary bracket radii.
 *
 * @see DESIGN.md — Components — app-empty-state
 *
 * @fileoverview Pawrrtal empty-state primitive.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';

/** Visual recipe for the empty state shell. */
export type AppEmptyStateTone = 'sidebar' | 'page' | 'card' | 'panel';

export interface AppEmptyStateProps {
  /** Layout variant — sidebar compact, editorial page, elevated card, or dashed settings panel. */
  tone: AppEmptyStateTone;
  /** Decorative icon (pass Lucide or SVG with aria-hidden as needed). */
  icon: React.ReactNode;
  /** Primary heading (also used as the single line for `inlineCta`). */
  title: string;
  /** Supporting copy; omit when using `layout="inlineCta"` if not needed. */
  description?: string;
  /**
   * Primary action. For **`layout="inlineCta"`**, only **`onClick`** is used — the
   * button label is **`title`**.
   */
  action?: {
    onClick: () => void;
    /** Button label for default layouts; omit when using `inlineCta`. */
    label?: string;
    /** Optional ARIA label for accessibility. */
    ariaLabel?: string;
  };
  /**
   * `inlineCta` renders a single sidebar row button (e.g. “Create your first project”).
   * Requires **`action`**; **`description`** is ignored.
   */
  layout?: 'default' | 'inlineCta';
  /** Optional root class for the outer wrapper. */
  className?: string;
}

/**
 * Centred or inset empty placeholder with tone-consistent chrome.
 *
 * @returns Empty-state markup for the chosen tone and layout.
 */
export function AppEmptyState({
  tone,
  icon,
  title,
  description,
  action,
  layout = 'default',
  className,
}: AppEmptyStateProps): React.JSX.Element {
  if (layout === 'inlineCta') {
    if (!action) {
      throw new Error('AppEmptyState: inlineCta layout requires an action with onClick');
    }
    return (
      <button
        aria-label={action.ariaLabel}
        className={cn(
          'flex cursor-pointer items-center gap-1.5 rounded-control px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground',
          className
        )}
        onClick={action.onClick}
        type="button"
      >
        {icon}
        {title}
      </button>
    );
  }

  if (tone === 'panel') {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-3 rounded-[12px] border border-dashed border-border/60 bg-foreground/[0.02] px-6 py-16 text-center',
          className
        )}
      >
        <div className="flex size-10 items-center justify-center rounded-control bg-foreground/[0.05] text-muted-foreground">
          {icon}
        </div>
        <h3 className="text-sm font-medium text-foreground">{title}</h3>
        {description ? <p className="max-w-sm text-sm text-muted-foreground">{description}</p> : null}
      </div>
    );
  }

  if (tone === 'card') {
    return (
      <div className={cn('flex size-full items-center justify-center p-6', className)}>
        <div className="flex max-w-[360px] flex-col items-center gap-3 rounded-surface-lg border border-border bg-background-elevated p-8 text-center shadow-minimal">
          <span className="flex size-10 items-center justify-center rounded-full bg-foreground-5 text-muted-foreground">
            {icon}
          </span>
          <h2 className="font-display text-[18px] font-medium text-foreground">{title}</h2>
          {description ? <p className="text-[13px] leading-relaxed text-muted-foreground">{description}</p> : null}
          {action?.label ? (
            <button
              aria-label={action.ariaLabel}
              className="mt-2 inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full bg-foreground px-4 text-[13px] font-medium text-background transition-colors duration-150 ease-out hover:bg-foreground/90"
              onClick={action.onClick}
              type="button"
            >
              {action.label}
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  if (tone === 'page') {
    return (
      <div className={cn('flex size-full items-center justify-center px-6 py-10', className)}>
        <div className="flex max-w-[420px] flex-col items-center gap-3 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-foreground/[0.05] text-muted-foreground">
            {icon}
          </span>
          <h2 className="font-display text-[28px] leading-tight font-medium tracking-[-0.02em] text-balance text-foreground">
            {title}
          </h2>
          {description ? (
            <p className="text-[14px] leading-relaxed text-pretty text-muted-foreground">{description}</p>
          ) : null}
          {action?.label ? (
            <button
              aria-label={action.ariaLabel}
              className="mt-2 inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full bg-foreground px-4 text-[13px] font-medium text-background transition-[background-color,transform] duration-150 ease-out hover:bg-foreground/90 active:scale-[0.98] motion-reduce:transition-none"
              onClick={action.onClick}
              type="button"
            >
              {action.label}
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  // sidebar (default)
  return (
    <div className={cn('flex flex-1 flex-col items-center justify-center px-6 text-center', className)}>
      <div className="flex size-10 items-center justify-center rounded-soft bg-foreground/[0.03] text-muted-foreground/70 shadow-minimal">
        {icon}
      </div>
      <h3 className="mt-4 text-sm font-medium text-foreground">{title}</h3>
      {description ? (
        <p className="mt-1.5 max-w-[220px] text-xs leading-5 text-muted-foreground">{description}</p>
      ) : null}
      {action?.label ? (
        <button
          aria-label={action.ariaLabel}
          className="mt-4 inline-flex h-7 items-center rounded-soft bg-background px-3 text-xs font-medium shadow-minimal transition-colors hover:bg-foreground/[0.03]"
          onClick={action.onClick}
          type="button"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
}
