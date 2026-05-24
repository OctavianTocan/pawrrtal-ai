/**
 * Compact citation chip linking to sources.
 *
 * @fileoverview AI Elements — `inline-citation`.
 */

'use client';
import type { ComponentProps } from 'react';
import { Badge } from '@/components/ui/badge';
import { HoverCard, HoverCardTrigger } from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';

export type InlineCitationProps = ComponentProps<'span'>;

export const InlineCitation = ({ className, ...props }: InlineCitationProps) => (
	<span className={cn('group inline items-center gap-1', className)} {...props} />
);

export type InlineCitationTextProps = ComponentProps<'span'>;

export const InlineCitationText = ({ className, ...props }: InlineCitationTextProps) => (
	<span className={cn('transition-colors group-hover:bg-accent', className)} {...props} />
);

export type InlineCitationCardProps = ComponentProps<typeof HoverCard>;

export const InlineCitationCard = (props: InlineCitationCardProps) => (
	<HoverCard closeDelay={0} openDelay={0} {...props} />
);

export type InlineCitationCardTriggerProps = ComponentProps<typeof Badge> & {
	sources: string[];
};

export const InlineCitationCardTrigger = ({
	sources,
	className,
	...props
}: InlineCitationCardTriggerProps) => (
	<HoverCardTrigger asChild>
		<Badge className={cn('ml-1 rounded-full', className)} variant="secondary" {...props}>
			{sources[0] ? (
				<>
					{new URL(sources[0]).hostname} {sources.length > 1 && `+${sources.length - 1}`}
				</>
			) : (
				'unknown'
			)}
		</Badge>
	</HoverCardTrigger>
);
