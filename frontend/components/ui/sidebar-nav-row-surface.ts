/**
 * Shared hover / selection class-name builder for sidebar navigation rows.
 *
 * @fileoverview Extracted from `sidebar-nav-row.tsx` so the component file
 * only exports React components (react-doctor `only-export-components`).
 *
 * @see DESIGN.md — Components — sidebar-nav-row
 */

import { cn } from '@/lib/utils';

export interface SidebarNavRowSurfaceOptions {
  /** Whether the row represents the active route / selection. */
  selected?: boolean;
  /** Comfortable matches conversation + project rows; compact matches tasks nav. */
  density: 'comfortable' | 'compact';
  /** Conversation titles wrap — start-align; single-line nav rows center-align. */
  align?: 'start' | 'center';
  className?: string;
}

/**
 * Class names for the interactive surface of a sidebar nav row (hover + selected).
 *
 * Use on **`<button>`** or a **`role="button"`** container — {@link EntityRow}
 * keeps **`div` + role** to avoid nested **`<button>`** with dropdown triggers.
 */
export function sidebarNavRowSurfaceClassName({
  selected = false,
  density,
  align = 'center',
  className,
}: SidebarNavRowSurfaceOptions): string {
  const alignClass = align === 'start' ? 'items-start' : 'items-center';
  const densityClass =
    density === 'comfortable'
      ? cn(align === 'start' ? 'py-2 pl-2 pr-4' : 'min-h-9 p-2', 'text-sm')
      : cn('h-8 rounded-soft px-2 text-[13px] font-medium');

  return cn(
    'flex w-full cursor-pointer gap-2 text-left outline-none transition-colors duration-150 ease-out rounded-soft',
    alignClass,
    densityClass,
    selected
      ? 'bg-foreground/[0.07] text-foreground hover:bg-foreground/[0.07]'
      : 'text-foreground/85 hover:bg-foreground/[0.04] hover:text-foreground',
    'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
    className
  );
}
