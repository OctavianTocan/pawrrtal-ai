'use client';

import { AlertTriangleIcon, RefreshCwIcon } from 'lucide-react';
import { type ReactNode, useMemo, useState } from 'react';
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message';
import { Shimmer } from '@/components/ai-elements/shimmer';
import { AgentSpinner } from '@/components/ui/agent-spinner';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { ArtifactCard } from '../artifacts/ArtifactCard';
import { extractToolChips, type ToolResultChips } from '../tool-result-parsers';
import type { ChatArtifactPayload, ChatTimelineEntry, ChatToolCall } from '../types';
import { ChainOfThought } from './ChainOfThought';
import { ReplyActionsRow } from './ReplyActionsRow';
import { ThinkingHeader } from './ThinkingHeader';

/**
 * Props for {@link AssistantMessage}.
 */
interface AssistantMessageProps {
	/** Plain-text response body (markdown rendered via Streamdown). */
	content: string;
	/** Reasoning text accumulated from `thinking` SSE events. */
	thinking?: string;
	/** Tool invocations captured during the assistant turn. */
	toolCalls?: ChatToolCall[];
	/** Arrival-ordered list of thinking bursts and tool invocations. */
	timeline?: ChatTimelineEntry[];
	/** Rendering status for this assistant turn. */
	status: AssistantMessageStatus;
	/** Total reasoning duration (whole seconds) — only set after streaming. */
	thinkingDurationSeconds?: number;
	/** Copy the response body to the clipboard. */
	onCopy?: () => void;
	/** Re-run the assistant turn for this message. */
	onRegenerate?: () => void;
	/** Artifacts the agent rendered during this turn (preview cards). */
	artifacts?: ChatArtifactPayload[];
}

interface AssistantMessageStatus {
	/** Whether this row's copy button should currently render its "Copied!" state. */
	isCopied?: boolean;
	/** Whether this turn ended in a stream-level error. */
	isFailed?: boolean;
	/** Whether a regeneration request is currently in flight for this row. */
	isRegenerating?: boolean;
	/** Whether the assistant is still streaming this message. */
	isStreaming: boolean;
}

/** Default state for messages without any chip data. */
const EMPTY_CHIPS: ToolResultChips = {
	webSources: [],
	calendarEvents: [],
	memoryResults: [],
};

/**
 * Collapsible chain-of-thought panel.
 *
 * Header is the {@link ThinkingHeader} (gradient text + animated dots while
 * streaming, duration label when done). Body is the {@link ChainOfThought}
 * rail. The wrapper deliberately has no left border or padding — the rail
 * carries the visual structure on its own. Mounted only when there is
 * something to show (thinking text or tool steps).
 */
function ReasoningPanel({
	timeline,
	toolCallsById,
	chipsByToolId,
	isStreaming,
	durationSeconds,
}: {
	timeline: ChatTimelineEntry[];
	toolCallsById: Map<string, ChatToolCall>;
	chipsByToolId: Map<string, ToolResultChips>;
	isStreaming: boolean;
	durationSeconds: number | undefined;
}): ReactNode {
	const [isOpen, setIsOpen] = useState<boolean>(true);

	return (
		<Collapsible className="not-prose mb-3 max-w-prose" onOpenChange={setIsOpen} open={isOpen}>
			<ThinkingHeader
				durationSeconds={durationSeconds}
				hasExpandableContent
				isOpen={isOpen}
				isStreaming={isStreaming}
				onToggle={() => setIsOpen((value) => !value)}
			/>
			<CollapsibleContent
				className={cn(
					'mt-2',
					'data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2',
					'data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2',
					'data-[state=closed]:animate-out data-[state=open]:animate-in'
				)}
			>
				<ChainOfThought
					chipsByToolId={chipsByToolId}
					timeline={timeline}
					toolCallsById={toolCallsById}
				/>
			</CollapsibleContent>
		</Collapsible>
	);
}

/**
 * Render a failed assistant turn: error banner with the backend message and a
 * Retry button that wraps `onRegenerate`. Hidden when there is no error text.
 */
function FailedReplyBanner({
	content,
	onRetry,
	isRetrying,
}: {
	content: string;
	onRetry?: () => void;
	isRetrying?: boolean;
}): ReactNode {
	return (
		<div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-destructive text-sm">
			<AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
			<div className="flex-1">
				<MessageResponse className="text-destructive">{content}</MessageResponse>
				{onRetry ? (
					<Button
						aria-label="Retry"
						className="mt-2 h-7 gap-1.5 px-2 text-destructive text-xs hover:bg-destructive/10 hover:text-destructive"
						disabled={isRetrying}
						onClick={onRetry}
						size="sm"
						type="button"
						variant="ghost"
					>
						<RefreshCwIcon
							className={cn('size-3.5', isRetrying ? 'animate-spin' : null)}
						/>
						{isRetrying ? 'Retrying' : 'Retry'}
					</Button>
				) : null}
			</div>
		</div>
	);
}

/**
 * Synthesise an arrival-order timeline from a message that doesn't have one.
 *
 * Live-streamed messages always have a `timeline`, but server-rendered
 * history is just `role` + `content` so the renderer needs a fallback view —
 * single thinking burst followed by every tool call in the order they appear.
 */
function buildEffectiveTimeline(
	timeline: ChatTimelineEntry[] | undefined,
	thinking: string | undefined,
	toolCalls: ChatToolCall[] | undefined
): ChatTimelineEntry[] {
	if (timeline && timeline.length > 0) return timeline;
	const synthesised: ChatTimelineEntry[] = [];
	if (thinking) synthesised.push({ kind: 'thinking', text: thinking });
	for (const call of toolCalls ?? []) {
		synthesised.push({ kind: 'tool', toolCallId: call.id });
	}
	return synthesised;
}

/**
 * Renders an assistant turn: chronologically-interleaved chain-of-thought
 * inside a collapsible reasoning panel, the markdown response body, and the
 * reply-action toolbar. Hides each section when its data is empty so a plain
 * answer (no thinking, no tools) reads identically to the previous UI.
 */
export function AssistantMessage({
	content,
	thinking,
	toolCalls,
	timeline,
	status,
	thinkingDurationSeconds,
	onCopy,
	onRegenerate,
	artifacts,
}: AssistantMessageProps): ReactNode {
	const { isCopied, isFailed, isRegenerating, isStreaming } = status;
	const hasContent = content.length > 0;
	const hasThinking = Boolean(thinking && thinking.length > 0);
	const hasTools = Boolean(toolCalls && toolCalls.length > 0);
	const showInitialLoader = isStreaming && !hasContent && !hasThinking && !hasTools && !isFailed;

	// Pre-compute tool indexing + chip parsing once per render so the
	// chain-of-thought renderer can dereference everything without recomputing
	// per child.
	const toolCallsById = useMemo(() => {
		const map = new Map<string, ChatToolCall>();
		for (const call of toolCalls ?? []) map.set(call.id, call);
		return map;
	}, [toolCalls]);

	const chipsByToolId = useMemo(() => {
		const map = new Map<string, ToolResultChips>();
		for (const call of toolCalls ?? []) {
			map.set(
				call.id,
				call.result === undefined ? EMPTY_CHIPS : extractToolChips(call.name, call.result)
			);
		}
		return map;
	}, [toolCalls]);

	const effectiveTimeline = useMemo(
		() => buildEffectiveTimeline(timeline, thinking, toolCalls),
		[timeline, thinking, toolCalls]
	);

	const showReasoningPanel = hasThinking || hasTools;
	const showActions = !isStreaming && !isFailed && (Boolean(onCopy) || Boolean(onRegenerate));

	return (
		<Message from="assistant">
			<MessageContent>
				{showInitialLoader ? (
					<div className="flex items-center gap-2 text-muted-foreground text-sm">
						<AgentSpinner size={16} />
						<Shimmer duration={1.2}>Thinking&hellip;</Shimmer>
					</div>
				) : null}

				{showReasoningPanel ? (
					<ReasoningPanel
						chipsByToolId={chipsByToolId}
						durationSeconds={thinkingDurationSeconds}
						isStreaming={isStreaming && !hasContent && !isFailed}
						timeline={effectiveTimeline}
						toolCallsById={toolCallsById}
					/>
				) : null}

				{isFailed && hasContent ? (
					<FailedReplyBanner
						content={content}
						isRetrying={isRegenerating}
						onRetry={onRegenerate}
					/>
				) : null}

				{hasContent && !isFailed ? <MessageResponse>{content}</MessageResponse> : null}

				{artifacts && artifacts.length > 0 ? (
					<div className="mt-3 flex flex-col gap-2">
						{artifacts.map((a) => (
							<ArtifactCard artifact={a} key={a.id} />
						))}
					</div>
				) : null}

				{showActions ? (
					<ReplyActionsRow
						isCopied={isCopied}
						isRegenerating={isRegenerating}
						onCopy={onCopy}
						onRegenerate={onRegenerate}
					/>
				) : null}
			</MessageContent>
		</Message>
	);
}
