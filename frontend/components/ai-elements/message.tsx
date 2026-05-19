/**
 * User and assistant message row with content subcomponents.
 *
 * @fileoverview AI Elements — `message`.
 */

'use client';

import type { FileUIPart, UIMessage } from 'ai';
import { ChevronLeftIcon, ChevronRightIcon, PaperclipIcon, XIcon } from 'lucide-react';
import Image from 'next/image';
import type { ComponentProps, HTMLAttributes, ReactElement } from 'react';
import { createContext, memo, use, useEffect, useReducer, useState } from 'react';
import { Streamdown } from 'streamdown';
import { Button } from '@/components/ui/button';
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
	from: UIMessage['role'];
};

export const Message = ({ className, from, ...props }: MessageProps) => (
	<div
		className={cn(
			'group flex w-full max-w-[95%] flex-col gap-2',
			from === 'user' ? 'is-user ml-auto justify-end' : 'is-assistant',
			className
		)}
		{...props}
	/>
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageContent = ({ children, className, ...props }: MessageContentProps) => (
	<div
		className={cn(
			// Base sizing flows from the design system (`--font-size-base` = 16px,
			// surfaced as `text-base`). `leading-relaxed` matches the body rhythm.
			// `gap-[13px]` (13px) keeps inter-block rhythm (thinking header → reasoning →
			// response) at a tighter beat than the previous 16px. Adjacent paragraph
			'is-user:dark flex w-fit max-w-full min-w-0 flex-col gap-[13px] overflow-hidden text-base leading-relaxed',
			// User bubble: asymmetric "tail" radii driven by the design-token
			// pair `--radius-bubble` / `--radius-bubble-tail`. The global
			// `--radius` is 0 so the standard `rounded-*` scale is no-op here —
			// this is the project's bubble token by design.
			'group-[.is-user]:ml-auto group-[.is-user]:rounded-[var(--radius-bubble)] group-[.is-user]:rounded-br-[var(--radius-bubble-tail)]',
			'group-[.is-user]:bg-user-message-bubble group-[.is-user]:px-4 group-[.is-user]:py-3 group-[.is-user]:text-foreground',
			'group-[.is-assistant]:text-foreground',
			className
		)}
		{...props}
	>
		{children}
	</div>
);

export type MessageActionsProps = ComponentProps<'div'>;

export const MessageActions = ({ className, children, ...props }: MessageActionsProps) => (
	<div className={cn('flex items-center gap-1', className)} {...props}>
		{children}
	</div>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
	tooltip?: string;
	label?: string;
};

export const MessageAction = ({
	tooltip,
	children,
	label,
	variant = 'ghost',
	size = 'icon-sm',
	...props
}: MessageActionProps) => {
	const button = (
		<Button size={size} type="button" variant={variant} {...props}>
			{children}
			<span className="sr-only">{label || tooltip}</span>
		</Button>
	);

	if (tooltip) {
		return (
			<TooltipProvider>
				<Tooltip>
					<TooltipTrigger asChild>{button}</TooltipTrigger>
					<TooltipContent>
						<p>{tooltip}</p>
					</TooltipContent>
				</Tooltip>
			</TooltipProvider>
		);
	}

	return button;
};

type MessageBranchContextType = {
	currentBranch: number;
	totalBranches: number;
	goToPrevious: () => void;
	goToNext: () => void;
	branches: ReactElement[];
	setBranches: (branches: ReactElement[]) => void;
};

const MessageBranchContext = createContext<MessageBranchContextType | null>(null);
const replaceNumberState = (_current: number, next: number): number => next;

const useMessageBranch = () => {
	const context = use(MessageBranchContext);

	if (!context) {
		throw new Error('MessageBranch components must be used within MessageBranch');
	}

	return context;
};

export type MessageBranchProps = HTMLAttributes<HTMLDivElement> & {
	defaultBranch?: number;
	onBranchChange?: (branchIndex: number) => void;
};

export const MessageBranch = ({
	defaultBranch = 0,
	onBranchChange,
	className,
	...props
}: MessageBranchProps) => {
	const [currentBranch, setCurrentBranch] = useReducer(replaceNumberState, defaultBranch);
	const [branches, setBranches] = useState<ReactElement[]>([]);

	const handleBranchChange = (newBranch: number) => {
		setCurrentBranch(newBranch);
		onBranchChange?.(newBranch);
	};

	const goToPrevious = () => {
		const newBranch = currentBranch > 0 ? currentBranch - 1 : branches.length - 1;
		handleBranchChange(newBranch);
	};

	const goToNext = () => {
		const newBranch = currentBranch < branches.length - 1 ? currentBranch + 1 : 0;
		handleBranchChange(newBranch);
	};

	const contextValue: MessageBranchContextType = {
		currentBranch,
		totalBranches: branches.length,
		goToPrevious,
		goToNext,
		branches,
		setBranches,
	};

	return (
		<MessageBranchContext.Provider value={contextValue}>
			<div className={cn('grid w-full gap-2 [&>div]:pb-0', className)} {...props} />
		</MessageBranchContext.Provider>
	);
};

export type MessageBranchContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageBranchContent = ({ children, ...props }: MessageBranchContentProps) => {
	const { currentBranch, setBranches, branches } = useMessageBranch();
	const childrenArray = Array.isArray(children) ? children : [children];

	// Use useEffect to update branches when they change
	useEffect(() => {
		if (branches.length !== childrenArray.length) {
			setBranches(childrenArray);
		}
	}, [childrenArray, branches, setBranches]);

	return childrenArray.map((branch, index) => (
		<div
			className={cn(
				'grid gap-2 overflow-hidden [&>div]:pb-0',
				index === currentBranch ? 'block' : 'hidden'
			)}
			key={branch.key}
			{...props}
		>
			{branch}
		</div>
	));
};

export type MessageBranchSelectorProps = HTMLAttributes<HTMLFieldSetElement> & {
	from: UIMessage['role'];
};

export const MessageBranchSelector = ({
	className,
	from,
	...props
}: MessageBranchSelectorProps) => {
	const { totalBranches } = useMessageBranch();

	// Don't render if there's only one branch
	if (totalBranches <= 1) {
		return null;
	}

	return (
		<ButtonGroup
			className="[&>*:not(:first-child)]:rounded-l-md [&>*:not(:last-child)]:rounded-r-md"
			orientation="horizontal"
			{...props}
		/>
	);
};

export type MessageBranchPreviousProps = ComponentProps<typeof Button>;

export const MessageBranchPrevious = ({ children, ...props }: MessageBranchPreviousProps) => {
	const { goToPrevious, totalBranches } = useMessageBranch();

	return (
		<Button
			aria-label="Previous branch"
			disabled={totalBranches <= 1}
			onClick={goToPrevious}
			size="icon-sm"
			type="button"
			variant="ghost"
			{...props}
		>
			{children ?? <ChevronLeftIcon size={14} />}
		</Button>
	);
};

export type MessageBranchNextProps = ComponentProps<typeof Button>;

export const MessageBranchNext = ({ children, className, ...props }: MessageBranchNextProps) => {
	const { goToNext, totalBranches } = useMessageBranch();

	return (
		<Button
			aria-label="Next branch"
			disabled={totalBranches <= 1}
			onClick={goToNext}
			size="icon-sm"
			type="button"
			variant="ghost"
			{...props}
		>
			{children ?? <ChevronRightIcon size={14} />}
		</Button>
	);
};

export type MessageBranchPageProps = HTMLAttributes<HTMLSpanElement>;

export const MessageBranchPage = ({ className, ...props }: MessageBranchPageProps) => {
	const { currentBranch, totalBranches } = useMessageBranch();

	return (
		<ButtonGroupText
			className={cn(
				'border-none bg-transparent text-muted-foreground shadow-none',
				className
			)}
			{...props}
		>
			{currentBranch + 1} of {totalBranches}
		</ButtonGroupText>
	);
};

export type MessageResponseProps = ComponentProps<typeof Streamdown>;

export const MessageResponse = memo(
	({ className, ...props }: MessageResponseProps) => (
		<Streamdown
			className={cn(
				// Base flow.
				'size-full text-sm leading-relaxed',
				// Reset edge margins so the bubble hugs content.
				'[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
				// Vertical rhythm — `my-4` = 16px under the project's
				// `--font-size-base = 16px`. Adjacent paragraph margins collapse
				// to the larger value, so two consecutive paragraphs render with a
				// 16px gap between them, matching the inter-block rhythm in
				// `MessageContent`. Tailwind spacing scale only, all wired to
				// project tokens in globals.css.
				'[&_p]:my-4 [&_p]:text-sm [&_p]:leading-normal',
				'[&_ul]:my-4 [&_ol]:my-4 [&_li]:my-0.5 [&_li]:leading-normal',
				// Pull nested paragraphs (e.g. inside list items) flush so each
				// bullet sits as one tight unit instead of acquiring my-4 again.
				'[&_li_p]:my-0',
				'[&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6',
				// Headings: text-lg / text-base / text-base = 18 / 16 / 16px under
				// the project's `--font-size-base = 16px`. Weight = semibold.
				// Heading margins collapse with adjacent paragraph `my-4` (16px)
				// so heading-to-paragraph gaps land at exactly 16px in either
				// direction.
				'[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-semibold',
				'[&_h2]:mt-4 [&_h2]:mb-1.5 [&_h2]:text-base [&_h2]:font-semibold',
				'[&_h3]:mt-3 [&_h3]:mb-1.5 [&_h3]:text-base [&_h3]:font-semibold',
				'[&_strong]:font-semibold',
				// Inline code: muted surface + mono font from the design-system stack.
				// Held one notch below body (text-sm = 14px) so monospace doesn't
				// bloom against proportional body type.
				'[&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-sm',
				className
			)}
			{...props}
		/>
	),
	(prevProps, nextProps) => prevProps.children === nextProps.children
);

MessageResponse.displayName = 'MessageResponse';

export type MessageAttachmentProps = HTMLAttributes<HTMLDivElement> & {
	data: FileUIPart;
	className?: string;
	onRemove?: () => void;
};

export function MessageAttachment({ data, className, onRemove, ...props }: MessageAttachmentProps) {
	const filename = data.filename || '';
	const mediaType = data.mediaType?.startsWith('image/') && data.url ? 'image' : 'file';
	const isImage = mediaType === 'image';
	const attachmentLabel = filename || (isImage ? 'Image' : 'Attachment');

	return (
		<div
			className={cn('group relative size-24 overflow-hidden rounded-lg', className)}
			{...props}
		>
			{isImage ? (
				<>
					<Image
						alt={filename || 'attachment'}
						className="size-full object-cover"
						height={100}
						src={data.url}
						unoptimized
						width={100}
					/>
					{onRemove && (
						<Button
							aria-label="Remove attachment"
							className="absolute top-2 right-2 size-6 rounded-full bg-background/80 p-0 opacity-0 backdrop-blur-sm transition-opacity hover:bg-background group-hover:opacity-100 [&>svg]:size-3"
							onClick={(e) => {
								e.stopPropagation();
								onRemove();
							}}
							type="button"
							variant="ghost"
						>
							<XIcon />
							<span className="sr-only">Remove</span>
						</Button>
					)}
				</>
			) : (
				<>
					<Tooltip>
						<TooltipTrigger asChild>
							<div className="flex size-full shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
								<PaperclipIcon className="size-4" />
							</div>
						</TooltipTrigger>
						<TooltipContent>
							<p>{attachmentLabel}</p>
						</TooltipContent>
					</Tooltip>
					{onRemove && (
						<Button
							aria-label="Remove attachment"
							className="size-6 shrink-0 rounded-full p-0 opacity-0 transition-opacity hover:bg-accent group-hover:opacity-100 [&>svg]:size-3"
							onClick={(e) => {
								e.stopPropagation();
								onRemove();
							}}
							type="button"
							variant="ghost"
						>
							<XIcon />
							<span className="sr-only">Remove</span>
						</Button>
					)}
				</>
			)}
		</div>
	);
}

export type MessageAttachmentsProps = ComponentProps<'div'>;

export function MessageAttachments({ children, className, ...props }: MessageAttachmentsProps) {
	if (!children) {
		return null;
	}

	return (
		<div className={cn('ml-auto flex w-fit flex-wrap items-start gap-2', className)} {...props}>
			{children}
		</div>
	);
}

export type MessageToolbarProps = ComponentProps<'div'>;

export const MessageToolbar = ({ className, children, ...props }: MessageToolbarProps) => (
	<div
		className={cn('mt-4 flex w-full items-center justify-between gap-4', className)}
		{...props}
	>
		{children}
	</div>
);
