/**
 * Skeleton loading primitive — re-exports boneyard-js.
 *
 * Boneyard wraps real content: `<Skeleton loading={true}>` shows bones,
 * `<Skeleton loading={false}>` renders children. For legacy call sites
 * that used the old placeholder-div pattern, use `<SkeletonBlock>`.
 */

export { Skeleton } from 'boneyard-js/react';
export type { SkeletonProps } from 'boneyard-js/react';

import { cn } from '@/lib/utils';

/**
 * Simple rectangular skeleton placeholder (legacy pattern).
 *
 * A plain pulsing div for cases where the boneyard wrapper pattern
 * doesn't fit (e.g. inline placeholder blocks inside a layout).
 */
export function SkeletonBlock({
	className,
	...props
}: React.ComponentProps<'div'>): React.JSX.Element {
	return (
		<div
			data-slot="skeleton"
			className={cn('bg-muted rounded-xl animate-pulse', className)}
			{...props}
		/>
	);
}
