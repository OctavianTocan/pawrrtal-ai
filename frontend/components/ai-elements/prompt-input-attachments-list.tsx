/**
 * Attachment list renderer for the current prompt input.
 *
 * @fileoverview AI Elements — prompt input attachments list subcomponent.
 */

'use client';

import type { FileUIPart } from 'ai';
import { Fragment, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { usePromptInputAttachments } from './prompt-input-context';

/** Props for rendering the current attachment list. */
export type PromptInputAttachmentsProps = Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {
	children: (attachment: FileUIPart & { id: string }) => ReactNode;
};

/** Attachment list renderer for the current prompt input. */
export function PromptInputAttachments({
	children,
	className,
	...props
}: PromptInputAttachmentsProps) {
	const attachments = usePromptInputAttachments();

	if (!attachments.files.length) {
		return null;
	}

	return (
		<div className={cn('flex w-full flex-wrap items-center gap-2 p-3', className)} {...props}>
			{attachments.files.map((file) => (
				<Fragment key={file.id}>{children(file)}</Fragment>
			))}
		</div>
	);
}
