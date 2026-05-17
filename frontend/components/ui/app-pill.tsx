/**
 * Compact status / metadata chips (integration badges, tag chips, inline counts).
 *
 * Tones map to semantic colors in **`globals.css`** instead of literal emerald/amber
 * utility classes. **`shape="pill"`** is uppercase micro-label (integration rows);
 * **`shape="tag"`** is sentence-case metadata (task **`#tags`**).
 *
 * @see DESIGN.md — Components — app-pill
 *
 * @fileoverview Pill and tag primitive for Pawrrtal.
 */

import type * as React from 'react';
import { cn } from '@/lib/utils';

export type AppPillTone = 'neutral' | 'info' | 'success' | 'warning' | 'destructive';

export type AppPillShape = 'pill' | 'tag';

export interface AppPillProps {
	tone: AppPillTone;
	shape: AppPillShape;
	children: React.ReactNode;
	className?: string;
}

const TONE_CLASS: Record<AppPillTone, string> = {
	neutral: 'bg-foreground/10 text-foreground',
	info: 'bg-info/15 text-info-text',
	success: 'bg-success/15 text-success-text',
	warning: 'bg-info/15 text-info-text',
	destructive: 'bg-destructive/15 text-destructive-text',
};

const SHAPE_CLASS: Record<AppPillShape, string> = {
	pill: 'rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide',
	tag: 'inline-flex h-5 items-center gap-0.5 rounded-md px-1.5 text-[11px] font-medium text-muted-foreground',
};

/**
 * Rounded pill or tag chip with semantic tone backgrounds.
 *
 * @returns Inline chip element.
 */
export function AppPill({ tone, shape, children, className }: AppPillProps): React.JSX.Element {
	const toneClasses =
		shape === 'tag' && tone === 'neutral' ? 'bg-foreground/[0.04]' : TONE_CLASS[tone];
	return (
		<span
			className={cn(
				'inline-flex items-center justify-center',
				SHAPE_CLASS[shape],
				toneClasses,
				className
			)}
		>
			{children}
		</span>
	);
}
