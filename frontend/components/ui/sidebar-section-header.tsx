/**
 * Section headings inside sidebars — collapsible date/project groups and
 * uppercase micro-labels for nested nav (tasks lists).
 *
 * Collapsible rows paint the shared hover tray (`group-hover/header:bg-foreground/2`)
 * so the hit target matches chat date groups and the Projects block.
 *
 * @see DESIGN.md — Components — sidebar-section-header
 *
 * @fileoverview Sidebar section header primitive for Pawrrtal.
 */

import { ChevronRight } from 'lucide-react';
import type * as React from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export type SidebarSectionHeaderProps =
	| CollapsibleSidebarSectionHeaderProps
	| StaticSidebarSectionHeaderProps;

interface CollapsibleSidebarSectionHeaderProps {
	variant: 'collapsible';
	/** Visible section title (e.g. "Today", "Projects"). */
	label: string;
	isCollapsed: boolean;
	onToggle: () => void;
	/** Shown after the label when collapsed — e.g. hidden conversation count. */
	collapsedMetaCount?: number;
	/** Absolutely positioned control (e.g. "Create project" icon). */
	trailingSlot?: React.ReactNode;
	/** Extra a11y props for the collapse **`&lt;button&gt;`** (e.g. **`aria-expanded`**). */
	toggleButtonProps?: Pick<
		ButtonHTMLAttributes<HTMLButtonElement>,
		'aria-expanded' | 'aria-label' | 'aria-controls'
	>;
	className?: string;
}

interface StaticSidebarSectionHeaderProps {
	variant: 'static';
	label: string;
	className?: string;
}

/**
 * Collapsible group control or static uppercase label for sidebar subsections.
 *
 * @returns Header markup — not wrapped in **`&lt;li&gt;`** (callers own list semantics).
 */
export function SidebarSectionHeader(props: SidebarSectionHeaderProps): React.JSX.Element {
	if (props.variant === 'static') {
		return (
			<p
				className={cn(
					'px-2 text-[11px] font-semibold tracking-[0.04em] text-muted-foreground/80 uppercase',
					props.className
				)}
			>
				{props.label}
			</p>
		);
	}

	const {
		label,
		isCollapsed,
		onToggle,
		collapsedMetaCount,
		trailingSlot,
		toggleButtonProps,
		className,
	} = props;

	return (
		<div className={cn('group/header relative', className)}>
			<button
				className="relative flex w-full cursor-pointer items-center gap-1.5 px-4 py-2"
				onClick={onToggle}
				type="button"
				{...toggleButtonProps}
			>
				<div className="pointer-events-none absolute inset-y-0.5 left-2 right-2 rounded-control transition-colors group-hover/header:bg-foreground/2" />
				<ChevronRight
					className={cn(
						'relative size-3.5 text-muted-foreground/60 transition-transform',
						!isCollapsed && 'rotate-90'
					)}
				/>
				<span className="relative text-sm font-medium text-muted-foreground">
					{label}
					{isCollapsed && collapsedMetaCount !== undefined ? (
						<>
							{' · '}
							<span className="text-muted-foreground/50">{collapsedMetaCount}</span>
						</>
					) : null}
				</span>
			</button>
			{trailingSlot}
		</div>
	);
}
