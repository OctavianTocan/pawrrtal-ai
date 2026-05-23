/**
 * Collapsible content panel displaying reasoning text.
 *
 * @fileoverview AI Elements — `reasoning` content subcomponent.
 */

'use client';

import type { ComponentProps } from 'react';
import { memo } from 'react';
import { Streamdown } from 'streamdown';
import { CollapsibleContent } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

export type ReasoningContentProps = ComponentProps<typeof CollapsibleContent> & {
	children: string;
};

export const ReasoningContent = memo(({ className, children, ...props }: ReasoningContentProps) => (
	<CollapsibleContent
		className={cn(
			'mt-4 text-sm',
			'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 text-muted-foreground outline-none data-[state=closed]:animate-out data-[state=open]:animate-in',
			className
		)}
		{...props}
	>
		<Streamdown className="text-sm [&_p]:text-sm [&_p]:leading-normal">{children}</Streamdown>
	</CollapsibleContent>
));

ReasoningContent.displayName = 'ReasoningContent';
