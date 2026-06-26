/**
 * Shared hover / selection chrome for sidebar navigation rows (conversations,
 * projects, tasks lists).
 *
 * Hover uses **`bg-foreground/[0.04]`**; selected uses **`bg-foreground/[0.07]`**
 * so primary navigation reads consistently across features.
 *
 * **Entity rows** use **`density="comfortable"`** + **`align="start"`** because
 * titles can wrap to two lines. **Project** and **tasks** nav rows use
 * **`align="center"`**; tasks uses **`density="compact"`** for the tighter list.
 *
 * @see DESIGN.md — Components — sidebar-nav-row
 *
 * @fileoverview Sidebar row surface tokens for Pawrrtal.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';
import { sidebarNavRowSurfaceClassName } from './sidebar-nav-row-surface';

export interface SidebarNavRowProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isSelected?: boolean;
  density?: 'comfortable' | 'compact';
  align?: 'start' | 'center';
  ref?: React.Ref<HTMLButtonElement>;
}

/**
 * Native **`&lt;button&gt;`** sidebar row with shared tokens (projects list, tasks nav).
 *
 * @returns A button element suitable for **`&lt;li&gt;`** children.
 */
export function SidebarNavRow({
  isSelected = false,
  density = 'comfortable',
  align = 'center',
  className,
  type = 'button',
  ref,
  ...props
}: SidebarNavRowProps): React.JSX.Element {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(sidebarNavRowSurfaceClassName({ selected: isSelected, density, align }), className)}
      {...props}
    />
  );
}
