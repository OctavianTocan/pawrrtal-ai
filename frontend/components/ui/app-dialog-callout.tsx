/**
 * Trust / info strip inside {@link AppDialog} bodies (not page-level alerts).
 *
 * Replaces one-off **`rounded-[10px] bg-foreground/[0.05]`** vs **`rounded-[8px]`**
 * mixes with a single **`rounded-soft`** shell and tone-specific backgrounds.
 *
 * @see DESIGN.md — Components — app-dialog-callout
 *
 * @fileoverview Inline dialog callout primitive for Pawrrtal.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';

export type AppDialogCalloutTone = 'info' | 'warning';

export interface AppDialogCalloutProps {
	/** Visual emphasis — info uses a slightly stronger tray than warning. */
	tone: AppDialogCalloutTone;
	/** Leading glyph (decorative — parent sets **`aria-hidden`** as appropriate). */
	icon: React.ReactNode;
	children: React.ReactNode;
	className?: string;
}

/**
 * Inline aside for supplementary dialog copy next to an icon.
 *
 * @returns Accessible complementary region inside the dialog body.
 */
export function AppDialogCallout({
	tone,
	icon,
	children,
	className,
}: AppDialogCalloutProps): React.JSX.Element {
	return (
		<aside
			className={cn(
				'flex items-start gap-3 rounded-soft p-3 text-sm leading-snug text-muted-foreground',
				tone === 'info' ? 'bg-foreground/[0.05]' : 'bg-foreground/[0.04]',
				className
			)}
		>
			<span className="mt-0.5 shrink-0">{icon}</span>
			<div className="min-w-0">{children}</div>
		</aside>
	);
}
