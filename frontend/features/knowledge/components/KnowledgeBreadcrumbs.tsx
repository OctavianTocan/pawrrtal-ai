'use client';

/**
 * Pill-style breadcrumb rendered at the top of the file/file-list panes.
 *
 * The breadcrumb is a row of soft pills with no chevron between them —
 * inactive segments render as muted text on transparent background, the
 * trailing (active) segment gets a soft `--foreground-5` pill so it reads
 * as "you are here" without a separator glyph.
 */

import { Fragment, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { KnowledgeBreadcrumb } from '../path-utils';

interface KnowledgeBreadcrumbsProps {
  /** Breadcrumb segments — first is the root, last is the current location. */
  crumbs: readonly KnowledgeBreadcrumb[];
  /** Fired when a non-current crumb is clicked. */
  onNavigate: (path: string) => void;
}

/**
 * Pure presentation. The container builds the crumb list via
 * `buildBreadcrumbs(...)` from `path-utils` and translates `onNavigate`
 * into a `router.replace` with the appropriate query string.
 */
export function KnowledgeBreadcrumbs({ crumbs, onNavigate }: KnowledgeBreadcrumbsProps): ReactNode {
  return (
    <nav aria-label="Knowledge breadcrumb" className="flex flex-wrap items-center gap-0.5">
      {crumbs.map((crumb, index) => (
        <Fragment key={`${crumb.path}-${index.toString()}`}>
          {crumb.isCurrent ? (
            <span
              className="rounded-md bg-foreground-5 px-2 py-1 text-[13px] font-medium text-foreground"
              aria-current="page"
            >
              {crumb.label}
            </span>
          ) : (
            <button
              type="button"
              onClick={() => onNavigate(crumb.path)}
              className={cn(
                'cursor-pointer rounded-md px-2 py-1 text-[13px] font-medium text-muted-foreground transition-colors duration-150 ease-out',
                'hover:bg-foreground-5 hover:text-foreground'
              )}
            >
              {crumb.label}
            </button>
          )}
        </Fragment>
      ))}
    </nav>
  );
}
