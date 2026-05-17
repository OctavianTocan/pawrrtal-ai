/**
 * Single labelled control row for {@link AppDialog} bodies and compact forms.
 *
 * Locks label density (**`text-sm font-medium`**) and spacing so modal fields
 * do not drift between **`text-xs`** / raw **`&lt;label&gt;`** mixes. For full
 * settings-style forms outside dialogs, continue using **`Field`** /
 * **`FieldLabel`** from **`field.tsx`**.
 *
 * @see DESIGN.md — Components — app-form-row
 *
 * @fileoverview Dialog-scoped form row primitive for Pawrrtal.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';

export interface AppFormRowProps {
	/** Associates the label with the control (`Input` `id`). */
	htmlFor: string;
	/** Visible or screen-reader-only legend for the control. */
	label: React.ReactNode;
	/** Use **`sr-only`** when a visible title lives in **`ModalDescription`**. */
	labelVisibility?: 'visible' | 'sr-only';
	/** Helper shown below the control. */
	description?: React.ReactNode;
	/** Validation message; renders in destructive color. */
	error?: string;
	/** The input, textarea, or other single control. */
	children: React.ReactNode;
	className?: string;
}

/**
 * Label + control stack with optional helper and error text.
 *
 * @returns Markup for one labelled field inside a dialog body.
 */
export function AppFormRow({
	htmlFor,
	label,
	labelVisibility = 'visible',
	description,
	error,
	children,
	className,
}: AppFormRowProps): React.JSX.Element {
	return (
		<div className={cn('flex flex-col gap-2', className)}>
			<label
				className={cn(
					labelVisibility === 'sr-only'
						? 'sr-only'
						: 'text-sm font-medium text-foreground'
				)}
				htmlFor={htmlFor}
			>
				{label}
			</label>
			{children}
			{description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
			{error ? (
				<p className="text-xs text-destructive" role="alert">
					{error}
				</p>
			) : null}
		</div>
	);
}
