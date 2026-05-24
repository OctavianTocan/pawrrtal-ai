/**
 * Scroll region with stick-to-bottom behavior for message lists.
 *
 * @fileoverview AI Elements — `conversation`.
 */

'use client';

import type { ComponentProps } from 'react';
import { StickToBottom } from 'use-stick-to-bottom';
import { cn } from '@/lib/utils';

export {
	ConversationEmptyState,
	type ConversationEmptyStateProps,
} from './conversation-empty-state';

export type ConversationProps = ComponentProps<typeof StickToBottom>;

export const Conversation = ({ className, ...props }: ConversationProps) => (
	<StickToBottom
		className={cn('relative flex-1 overflow-y-hidden', className)}
		initial="smooth"
		resize="smooth"
		role="log"
		{...props}
	/>
);

export type ConversationContentProps = ComponentProps<typeof StickToBottom.Content>;

export const ConversationContent = ({ className, ...props }: ConversationContentProps) => (
	<StickToBottom.Content className={cn('flex flex-col gap-8 p-4', className)} {...props} />
);
