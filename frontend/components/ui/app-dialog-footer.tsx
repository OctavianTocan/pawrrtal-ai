/**
 * Primary action row for {@link AppDialog} **`footer`** slots.
 *
 * Default layout stacks actions **bottom-first** on narrow viewports
 * (`flex-col-reverse`) then aligns end on **`sm+`**, matching destructive and
 * rename flows without clipping thumbs on phones.
 *
 * @see DESIGN.md — Components — app-dialog-footer
 *
 * @fileoverview Dialog footer layout primitive for Pawrrtal.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';

export interface AppDialogFooterProps {
	children: React.ReactNode;
	/** Horizontal alignment after the **`sm`** breakpoint. */
	align?: 'end' | 'between';
	className?: string;
}

/**
 * Responsive footer tray for dialog primary and secondary actions.
 *
 * @returns Footer markup for `AppDialog` **`footer`** prop.
 */
export function AppDialogFooter({
	children,
	align = 'end',
	className,
}: AppDialogFooterProps): React.JSX.Element {
	return (
		<div
			className={cn(
				'flex flex-col-reverse gap-2 sm:flex-row',
				align === 'end' && 'sm:justify-end',
				align === 'between' && 'sm:justify-between',
				className
			)}
		>
			{children}
		</div>
	);
}
