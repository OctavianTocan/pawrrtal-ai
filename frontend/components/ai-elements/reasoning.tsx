/**
 * Expandable “thinking” panel for extended model rationale.
 *
 * @fileoverview AI Elements — `reasoning`.
 */

'use client';

import { useControllableState } from '@radix-ui/react-use-controllable-state';
import { BrainIcon, ChevronDownIcon } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import { createContext, memo, use, useEffect, useRef } from 'react';
import { Streamdown } from 'streamdown';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { Shimmer } from './shimmer';

type ReasoningContextValue = {
	isStreaming: boolean;
	isOpen: boolean;
	setIsOpen: (open: boolean) => void;
	duration: number | undefined;
};

const ReasoningContext = createContext<ReasoningContextValue | null>(null);

export const useReasoning = () => {
	const context = use(ReasoningContext);
	if (!context) {
		throw new Error('Reasoning components must be used within Reasoning');
	}
	return context;
};

export type ReasoningProps = ComponentProps<typeof Collapsible> & {
	isStreaming?: boolean;
	open?: boolean;
	defaultOpen?: boolean;
	onOpenChange?: (open: boolean) => void;
	duration?: number;
};

const AUTO_CLOSE_DELAY = 1000;
const MS_IN_S = 1000;

export const Reasoning = memo(
	({
		className,
		isStreaming = false,
		open,
		defaultOpen = true,
		onOpenChange,
		duration: durationProp,
		children,
		...props
	}: ReasoningProps) => {
		const [isOpen, setIsOpen] = useControllableState({
			prop: open,
			defaultProp: defaultOpen,
			onChange: onOpenChange,
		});
		const hasAutoClosedRef = useRef(false);
		const durationRef = useRef<number | undefined>(undefined);
		const startTimeRef = useRef<number | null>(null);
		if (isStreaming && startTimeRef.current === null) {
			startTimeRef.current = Date.now();
		}
		if (!isStreaming && startTimeRef.current !== null) {
			durationRef.current = Math.ceil((Date.now() - startTimeRef.current) / MS_IN_S);
			startTimeRef.current = null;
		}
		const duration = durationProp ?? durationRef.current;

		// Auto-open when streaming starts, auto-close when streaming ends (once only)
		useEffect(() => {
			if (defaultOpen && !isStreaming && isOpen && !hasAutoClosedRef.current) {
				// Add a small delay before closing to allow user to see the content
				const timer = setTimeout(() => {
					setIsOpen(false);
					hasAutoClosedRef.current = true;
				}, AUTO_CLOSE_DELAY);

				return () => clearTimeout(timer);
			}
		}, [isStreaming, isOpen, defaultOpen, setIsOpen]);

		const handleOpenChange = (newOpen: boolean) => {
			setIsOpen(newOpen);
		};

		return (
			<ReasoningContext.Provider value={{ isStreaming, isOpen, setIsOpen, duration }}>
				<Collapsible
					className={cn('not-prose mb-4', className)}
					onOpenChange={handleOpenChange}
					open={isOpen}
					{...props}
				>
					{children}
				</Collapsible>
			</ReasoningContext.Provider>
		);
	}
);

export type ReasoningTriggerProps = ComponentProps<typeof CollapsibleTrigger> & {
	getThinkingMessage?: (isStreaming: boolean, duration?: number) => ReactNode;
};

const defaultGetThinkingMessage = (isStreaming: boolean, duration?: number) => {
	if (isStreaming || duration === 0) {
		return <Shimmer duration={1}>Thinking&hellip;</Shimmer>;
	}
	if (duration === undefined) {
		return <p>Thought for a few seconds</p>;
	}
	return <p>Thought for {duration} seconds</p>;
};

export const ReasoningTrigger = memo(
	({
		className,
		children,
		getThinkingMessage = defaultGetThinkingMessage,
		...props
	}: ReasoningTriggerProps) => {
		const { isStreaming, isOpen, duration } = useReasoning();

		return (
			<CollapsibleTrigger
				className={cn(
					'flex w-full items-center gap-2 text-muted-foreground text-sm transition-colors hover:text-foreground',
					className
				)}
				{...props}
			>
				{children ?? (
					<>
						<BrainIcon className="size-4" />
						{getThinkingMessage(isStreaming, duration)}
						<ChevronDownIcon
							className={cn(
								'size-4 transition-transform',
								isOpen ? 'rotate-180' : 'rotate-0'
							)}
						/>
					</>
				)}
			</CollapsibleTrigger>
		);
	}
);

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

Reasoning.displayName = 'Reasoning';
ReasoningTrigger.displayName = 'ReasoningTrigger';
ReasoningContent.displayName = 'ReasoningContent';
